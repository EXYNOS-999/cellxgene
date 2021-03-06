from enum import Enum
import threading
import time
from server.data_common.rwlock import RWLock
from server.common.errors import DatasetAccessError
from server.common.data_locator import DataLocator
from contextlib import contextmanager


class MatrixDataCacheItem(object):
    """This class provides access and caching for a dataset.  The first time a dataset is accessed, it is
    opened and cached.  Later accesses use the cached version.   It may also be deleted by the
    MatrixDataCacheManager to make room for another dataset.  While a dataset is actively being used
    (during the lifetime of a api request), a reader lock is locked.  During that time, the dataset cannot
    be removed."""

    def __init__(self, loader):
        self.loader = loader
        self.data_adaptor = None
        self.data_lock = RWLock()

    def acquire_existing(self):
        """If the data_adaptor exists, take a read lock and return it, else return None"""
        self.data_lock.r_acquire()
        if self.data_adaptor:
            return self.data_adaptor

        self.data_lock.r_release()
        return None

    def acquire_and_open(self, app_config):
        """returns the data_adaptor if cached.  opens the data_adaptor if not.
        In either case, the a reader lock is taken.  Must call release when
        the data_adaptor is no longer needed"""
        self.data_lock.r_acquire()
        if self.data_adaptor:
            return self.data_adaptor
        self.data_lock.r_release()

        self.data_lock.w_acquire()
        # the data may have been loaded while waiting on the lock
        if not self.data_adaptor:
            try:
                self.loader.pre_load_validation()
                self.data_adaptor = self.loader.open(app_config)
            except Exception as e:
                # necessary to hold the reader lock after an exception, since
                # the release will occur when the context exits.
                self.data_lock.w_demote()
                raise e

        # demote the write lock to a read lock.
        self.data_lock.w_demote()
        return self.data_adaptor

    def release(self):
        """Release the reader lock"""
        self.data_lock.r_release()

    def delete(self):
        """Clear resources used by this dataset"""
        with self.data_lock.w_locked():
            if self.data_adaptor:
                self.data_adaptor.cleanup()
                self.data_adaptor = None


class MatrixDataCacheManager(object):
    """A class to manage the cached datasets.   This is intended to be used as a context manager
    for handling api requests.  When the context is created, the data_adator is either loaded or
    retrieved from a cache.  In either case, the reader lock is taken during this time, and release
    when the context ends.  This class currently implements a simple least recently used cache,
    which can delete a dataset from the cache to make room for a new oneo

    This is the intended usage pattern:

           m = MatrixDataCacheManager()
           with m.data_adaptor(location, app_config) as data_adaptor:
               # use the data_adaptor for some operation
    """

    #  The number of datasets to cache.  When MAX_CACHED is reached, the least recently used
    #  cache is replaced with the newly requested one.
    #  TODO:  This is very simple.  This can be improved by taking into account how much space is actually
    #         taken by each dataset, instead of arbitrarily picking a max datasets to cache.
    #         Also, this should be controlled by a configuration parameter.
    MAX_CACHED = 5

    @staticmethod
    def set_max_datasets(max_cached):
        MatrixDataCacheManager.MAX_CACHED = max_cached

    # FIXME:   If the number of active datasets exceeds the MAX_CACHED, then each request could
    # lead to a dataset being deleted and a new only being opened: the cache will get thrashed.
    # In this case, we may need to send back a 503 (Server Unavailable), or some other error message.

    # FIXME:  If the actual dataset is changed.  E.g. a new set of datafiles replaces an existing set,
    # then the cache will not react to this.   Ideally this would invalidate the cache.  One solution is
    # to keep a small metadata file associated with each dataset, which contains versioning information.
    # When the dataset is accessed, the current version can be compared with the cached version, and if
    # there is a mismatch, then the cache can be refreshed.

    def __init__(self):
        # key is location, value is tuple of (MatrixDataCacheItem, last_accessed)
        self.datasets = {}
        self.lock = threading.Lock()

    @contextmanager
    def data_adaptor(self, location, app_config):
        # create a loader for to this location if it does not already exist

        delete_adaptor = None
        data_adaptor = None

        with self.lock:
            value = self.datasets.get(location)
            if value is not None:
                cache_item = value[0]
                last_accessed = time.time()
                self.datasets[location] = (cache_item, last_accessed)
                data_adaptor = cache_item.acquire_existing()

            if data_adaptor is None:
                while True:
                    # find the last access times for each loader
                    if len(self.datasets) < self.MAX_CACHED:
                        break

                    items = list(self.datasets.items())
                    sorted(items, key=lambda x: x[1][1])
                    # close the least recently used loader
                    oldest = items[0]
                    oldest_cache = oldest[1][0]
                    oldest_key = oldest[0]
                    del self.datasets[oldest_key]
                    delete_adaptor = oldest_cache

                last_accessed = time.time()
                loader = MatrixDataLoader(location, app_config=app_config)
                cache_item = MatrixDataCacheItem(loader)
                self.datasets[location] = (cache_item, last_accessed)

        try:
            if delete_adaptor:
                delete_adaptor.delete()
            if data_adaptor is None:
                data_adaptor = cache_item.acquire_and_open(app_config)
            yield data_adaptor
        finally:
            cache_item.release()


class MatrixDataType(Enum):
    H5AD = "h5ad"
    CXG = "cxg"
    UNKNOWN = "unknown"


class MatrixDataLoader(object):
    def __init__(self, location, matrix_data_type=None, app_config=None):
        """ location can be a string or DataLocator """
        self.location = DataLocator(location, app_config)
        if not self.location.exists():
            raise DatasetAccessError("Dataset does not exist.")

        # matrix_data_type is an enum value of type MatrixDataType
        self.matrix_data_type = matrix_data_type
        # matrix_type is a DataAdaptor type, which corresonds to the matrix_data_type
        self.matrix_type = None

        if matrix_data_type is None:
            self.matrix_data_type = self.__matrix_data_type()

        if not self.__matrix_data_type_allowed(app_config):
            raise DatasetAccessError(f"Dataset does not have an allowed type.")

        if self.matrix_data_type == MatrixDataType.H5AD:
            from server.data_anndata.anndata_adaptor import AnndataAdaptor

            self.matrix_type = AnndataAdaptor
        elif self.matrix_data_type == MatrixDataType.CXG:
            from server.data_cxg.cxg_adaptor import CxgAdaptor

            self.matrix_type = CxgAdaptor

    def __matrix_data_type(self):
        if self.location.path.endswith(".h5ad"):
            return MatrixDataType.H5AD
        elif ".cxg" in self.location.path:
            return MatrixDataType.CXG
        else:
            return MatrixDataType.UNKNOWN

    def __matrix_data_type_allowed(self, app_config):
        if self.matrix_data_type == MatrixDataType.UNKNOWN:
            return False

        if not app_config:
            return True
        if not app_config.multi_dataset__dataroot:
            return True
        if len(app_config.multi_dataset__allowed_matrix_types) == 0:
            return True

        for val in app_config.multi_dataset__allowed_matrix_types:
            try:
                if self.matrix_data_type == MatrixDataType(val):
                    return True
            except ValueError:
                # Check case where multi_dataset_allowed_matrix_type does not have a
                # valid MatrixDataType value.  TODO:  Add a feature to check
                # the AppConfig for errors on startup
                return False

        return False

    def pre_load_validation(self):
        if self.matrix_data_type == MatrixDataType.UNKNOWN:
            raise DatasetAccessError(f"Dataset does not have a recognized type: .h5ad or .cxg")
        self.matrix_type.pre_load_validation(self.location)

    def file_size(self):
        return self.matrix_type.file_size(self.location)

    def open(self, app_config):
        # create and return a DataAdaptor object
        return self.matrix_type.open(self.location, app_config)
