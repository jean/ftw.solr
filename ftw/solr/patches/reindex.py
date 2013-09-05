from Acquisition import aq_base
from Products.Archetypes.config import TOOL_NAME
from Products.Archetypes.log import log
from Products.Archetypes.utils import isFactoryContained
from Products.CMFCore.interfaces import ICatalogTool
from Products.CMFCore.utils import getToolByName
from collective.indexing.queue import getQueue
from collective.indexing.queue import processQueue
from logging import WARNING
from plone.indexer.interfaces import IIndexer
from zope.component import queryMultiAdapter
import logging


logger = logging.getLogger('ftw.solr')

def is_index_value_equal(old, new):
    if type(old) != type(new):
        return False
    if isinstance(old, list):
        return set(old) == set(new)
    return old == new


def ftw_solr_CatalogMultiplex_reindexObjectSecurity(self, skip_self=False):
    """update security information in all registered catalogs.
    """
    if isFactoryContained(self):
        return
    at = getToolByName(self, TOOL_NAME, None)
    if at is None:
        return

    catalogs = [c for c in at.getCatalogsByType(self.meta_type)
                           if ICatalogTool.providedBy(c)]

    # Account for name mangling of double underscore attributes
    path = self._CatalogMultiplex__url()

    skipped = 0
    for catalog in catalogs:
        for brain in catalog.unrestrictedSearchResults(path=path):
            brain_path = brain.getPath()
            if brain_path == path and skip_self:
                continue

            # Get the object
            if hasattr(aq_base(brain), '_unrestrictedGetObject'):
                ob = brain._unrestrictedGetObject()
            else:
                # BBB: Zope 2.7
                ob = self.unrestrictedTraverse(brain_path, None)
            if ob is None:
                # BBB: Ignore old references to deleted objects.
                # Can happen only in Zope 2.7, or when using
                # catalog-getObject-raises off in Zope 2.8
                log("reindexObjectSecurity: Cannot get %s from catalog" %
                    brain_path, level=WARNING)
                continue

            indexed_values = catalog._catalog.getIndexDataForRID(brain.getRID())
            changed_indexes = []
            for index_name in self._cmf_security_indexes:
                indexer = queryMultiAdapter((ob, catalog), IIndexer,
                                            name=index_name)
                if indexer is None:
                    indexer = getattr(ob, index_name, None)

                if indexer is None:
                    changed_indexes.append(index_name)
                else:
                    new_value = indexer()
                    if not is_index_value_equal(indexed_values[index_name],
                                                new_value):
                        changed_indexes.append(index_name)

            if len(changed_indexes) > 0:
                print 'INDEXING', self, ob.absolute_url()
                print '        BEFORE:', indexed_values[index_name]
                print '         AFTER:', new_value
                indexer = getQueue()
                indexer.reindex(ob, changed_indexes)
            else:
                skipped += 1
    print 'SKIP', skipped


def ftw_solr_CatalogAware_reindexObjectSecurity(self, skip_self=False):
    """ Reindex security-related indexes on the object.
    """
    catalog = self._getCatalogTool()
    if catalog is None:
        return
    path = '/'.join(self.getPhysicalPath())

    # XXX if _getCatalogTool() is overriden we will have to change
    # this method for the sub-objects.
    for brain in catalog.unrestrictedSearchResults(path=path):
        brain_path = brain.getPath()
        if brain_path == path and skip_self:
            continue
        # Get the object
        ob = brain._unrestrictedGetObject()
        if ob is None:
            # BBB: Ignore old references to deleted objects.
            # Can happen only when using
            # catalog-getObject-raises off in Zope 2.8
            logger.warning("reindexObjectSecurity: Cannot get %s from "
                           "catalog", brain_path)
            continue
        # Recatalog with the same catalog uid.
        s = getattr(ob, '_p_changed', 0)

        # Also update relevant security indexes in solr
        indexer = getQueue()
        indexer.reindex(ob, self._cmf_security_indexes)

        if s is None: ob._p_deactivate()

