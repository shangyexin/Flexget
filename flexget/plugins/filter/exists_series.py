import copy
import os
import logging
from flexget.plugin import register_plugin, priority, PluginWarning
from flexget.utils.titles import SeriesParser, ParseWarning

log = logging.getLogger('exists_series')


class FilterExistsSeries(object):
    """
    Intelligent series aware exists rejecting.

    Example::

      exists_series: /storage/series/
    """

    def validator(self):
        from flexget import validator
        root = validator.factory()
        root.accept('path')
        bundle = root.accept('list')
        bundle.accept('path')
        advform = root.accept('dict')
        advform.accept('boolean', key='allow_different_qualities')
        advform.accept('equals', key='allow_different_qualities').accept('better')
        advform.accept('path', key='path')
        advform.accept('list', key='path').accept('path')
        return root

    def get_config(self, task):
        config = task.config.get('exists_series', [])
        # if config is not a dict, assign value to 'path' key
        if not isinstance(config, dict):
            config = {'path': config}
        # if only a single path is passed turn it into a 1 element list
        if isinstance(config['path'], basestring):
            config['path'] = [config['path']]
        return config

    @priority(-1)
    def on_task_filter(self, task):
        accepted_series = {}
        for entry in task.accepted:
            if 'series_parser' in entry:
                if entry['series_parser'].valid:
                    accepted_series.setdefault(entry['series_parser'].name, []).append(entry)
                else:
                    log.debug('entry %s series_parser invalid' % entry['title'])
        if not accepted_series:
            if task.accepted:
                log.warning('No accepted entries have series information. exists_series cannot filter them')
            else:
                log.debug('Scanning not needed')
            return

        config = self.get_config(task)
        for path in config.get('path'):
            log.verbose('Scanning %s' % path)
            # crashes on some paths with unicode
            path = str(os.path.expanduser(path))
            if not os.path.exists(path):
                raise PluginWarning('Path %s does not exist' % path, log)
            # scan through
            for root, dirs, files in os.walk(path):
                # convert filelists into utf-8 to avoid unicode problems
                dirs = [x.decode('utf-8', 'ignore') for x in dirs]
                files = [x.decode('utf-8', 'ignore') for x in files]
                # For speed, only test accepted entries since our priority should be after everything is accepted.
                for series in accepted_series:
                    # make new parser from parser in entry
                    disk_parser = copy.copy(accepted_series[series][0]['series_parser'])
                    for name in files + dirs:
                        # run parser on filename data
                        disk_parser.data = name
                        try:
                            disk_parser.parse(data=name)
                        except ParseWarning, pw:
                            from flexget.utils.log import log_once
                            log_once(pw.value, logger=log)
                        if disk_parser.valid:
                            log.debug('name %s is same series as %s' % (name, series))
                            log.debug('disk_parser.identifier = %s' % disk_parser.identifier)
                            log.debug('disk_parser.quality = %s' % disk_parser.quality)
                            log.debug('disk_parser.proper_count = %s' % disk_parser.proper_count)

                            for entry in accepted_series[series]:
                                log.debug('series_parser.identifier = %s' % entry['series_parser'].identifier)
                                if disk_parser.identifier != entry['series_parser'].identifier:
                                    log.trace('wrong identifier')
                                    continue
                                log.debug('series_parser.quality = %s' % entry['series_parser'].quality)
                                if config.get('allow_different_qualities') == 'better':
                                    if entry['series_parser'].quality > disk_parser.quality:
                                        log.trace('better quality')
                                        continue
                                elif config.get('allow_different_qualities'):
                                    if disk_parser.quality != entry['series_parser'].quality:
                                        log.trace('wrong quality')
                                        continue
                                log.debug('entry parser.proper_count = %s' % entry['series_parser'].proper_count)
                                if disk_parser.proper_count >= entry['series_parser'].proper_count:
                                    task.reject(entry, 'proper already exists')
                                    continue
                                else:
                                    log.trace('new one is better proper, allowing')
                                    continue

                                task.reject(entry, 'episode already exists')

register_plugin(FilterExistsSeries, 'exists_series', groups=['exists'])
