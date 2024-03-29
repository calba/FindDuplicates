#!/usr/bin/env python
# vim:fileencoding=UTF-8:ts=4:sw=4:sta:et:sts=4:ai
from __future__ import (unicode_literals, division, absolute_import,
                        print_function)

__license__   = 'GPL v3'
__copyright__ = '2011, Grant Drake <grant.drake@gmail.com>'
__docformat__ = 'restructuredtext en'

import copy
try:
    from PyQt5.Qt import (QWidget, QVBoxLayout, QPushButton)
except:
    from PyQt4.Qt import (QWidget, QVBoxLayout, QPushButton)
from calibre.gui2 import dynamic, info_dialog
from calibre.utils.config import JSONConfig
from calibre_plugins.find_duplicates.common_utils import (get_library_uuid, KeyboardConfigDialog,
                                                          PrefsViewerDialog)

PREFS_NAMESPACE = 'FindDuplicatesPlugin'
PREFS_KEY_SETTINGS = 'settings'

KEY_LAST_LIBRARY_COMPARE = 'lastLibraryCompare'
KEY_BOOK_EXEMPTIONS = 'bookExemptions'
KEY_AUTHOR_EXEMPTIONS = 'authorExemptions'

KEY_SCHEMA_VERSION = 'SchemaVersion'
DEFAULT_SCHEMA_VERSION = 1.5

DEFAULT_LIBRARIES_VALUES = {}
DEFAULT_LIBRARY_VALUES = {
                            KEY_LAST_LIBRARY_COMPARE: '',
                            KEY_BOOK_EXEMPTIONS: [],
                            KEY_AUTHOR_EXEMPTIONS: [],
                            KEY_SCHEMA_VERSION: DEFAULT_SCHEMA_VERSION
                         }

KEY_SEARCH_TYPE = 'searchType'
KEY_IDENTIFIER_TYPE = 'identifierType'
KEY_TITLE_MATCH = 'titleMatch'
KEY_AUTHOR_MATCH = 'authorMatch'
KEY_SHOW_ALL_GROUPS = 'showAllGroups'
KEY_SORT_GROUPS_TITLE = 'sortGroupsByTitle'
KEY_SHOW_TAG_AUTHOR = 'showTagAuthor'
KEY_TITLE_SOUNDEX = 'titleSoundexLength'
KEY_AUTHOR_SOUNDEX = 'authorSoundexLength'
KEY_PUBLISHER_SOUNDEX = 'publisherSoundexLength'
KEY_SERIES_SOUNDEX = 'seriesSoundexLength'
KEY_TAGS_SOUNDEX = 'tagsSoundexLength'
KEY_INCLUDE_LANGUAGES = 'includeLanguages'
KEY_AUTO_DELETE_BINARY_DUPS = 'autoDeleteBinaryDups'

KEY_SHOW_VARIATION_BOOKS = 'showVariationBooks'

# This is where all preferences for this plugin will be stored
plugin_prefs = JSONConfig('plugins/Find Duplicates')


def migrate_library_config_if_required(db, library_config):
    schema_version = library_config.get(KEY_SCHEMA_VERSION, 0)
    if schema_version == DEFAULT_SCHEMA_VERSION:
        return
    # We have changes to be made - mark schema as updated
    library_config[KEY_SCHEMA_VERSION] = DEFAULT_SCHEMA_VERSION

    # Any migration code in future will exist in here.
    #if schema_version < 1.x:

    set_library_config(db, library_config)


def get_library_config(db):
    library_id = get_library_uuid(db)
    library_config = None
    # Check whether this is a view needing to be migrated from json into database
    if 'libraries' in plugin_prefs:
        libraries = plugin_prefs['libraries']
        if library_id in libraries:
            # We will migrate this below
            library_config = libraries[library_id]
            # Cleanup from json file so we don't ever do this again
            del libraries[library_id]
            if len(libraries) == 0:
                # We have migrated the last library for this user
                del plugin_prefs['libraries']
            else:
                plugin_prefs['libraries'] = libraries

    if library_config is None:
        library_config = db.prefs.get_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS,
                                                 copy.deepcopy(DEFAULT_LIBRARY_VALUES))
    migrate_library_config_if_required(db, library_config)
    return library_config

def set_library_config(db, library_config):
    db.prefs.set_namespaced(PREFS_NAMESPACE, PREFS_KEY_SETTINGS, library_config)

def get_exemption_lists(db):
    # When migrating from v1.0 or earlier to v1.1, exemptions have changed
    # Too problematic to actually migrate the data, so just discard previous maps
    library_config = get_library_config(db)
    if 'bookNotDuplicates' in library_config:
        del library_config['bookNotDuplicates']
        set_exemption_list(db, KEY_BOOK_EXEMPTIONS, [])
    if 'authorNotDuplicates' in library_config:
        del library_config['authorNotDuplicates']
        set_exemption_list(db, KEY_AUTHOR_EXEMPTIONS, [])

    book_exemptions = library_config.get(KEY_BOOK_EXEMPTIONS, [])
    is_changed = False
    for idx in xrange(0, len(book_exemptions)):
        old_list = book_exemptions[idx]
        new_list = [book_id for book_id in old_list if db.data.has_id(book_id)]
        if len(old_list) != len(new_list):
            book_exemptions[idx] = new_list
            is_changed = True
    if is_changed:
        book_exemptions = [l for l in book_exemptions if len(l) > 0]
        set_exemption_list(db, KEY_BOOK_EXEMPTIONS, book_exemptions)

    author_exemptions = library_config.get(KEY_AUTHOR_EXEMPTIONS, [])
    return book_exemptions, author_exemptions

def set_exemption_list(db, config_key, exemptions_list):
    library_config = get_library_config(db)
    library_config[config_key] = exemptions_list
    set_library_config(db, library_config)


class ConfigWidget(QWidget):

    def __init__(self, plugin_action):
        QWidget.__init__(self)
        self.plugin_action = plugin_action
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        keyboard_shortcuts_button = QPushButton('Keyboard shortcuts...', self)
        keyboard_shortcuts_button.setToolTip(_(
                    'Edit the keyboard shortcuts associated with this plugin'))
        keyboard_shortcuts_button.clicked.connect(self.edit_shortcuts)
        layout.addWidget(keyboard_shortcuts_button)

        reset_confirmation_button = QPushButton(_('Reset disabled &confirmation dialogs'), self)
        reset_confirmation_button.setToolTip(_(
                    'Reset all show me again dialogs for the Find Duplicates plugin'))
        reset_confirmation_button.clicked.connect(self.reset_dialogs)
        layout.addWidget(reset_confirmation_button)
        view_prefs_button = QPushButton('&View library preferences...', self)
        view_prefs_button.setToolTip(_(
                    'View data stored in the library database for this plugin'))
        view_prefs_button.clicked.connect(self.view_prefs)
        layout.addWidget(view_prefs_button)
        layout.addStretch(1)

    def save_settings(self):
        # Delete the legacy keyboard setting options as no longer required
        if 'options' in plugin_prefs:
            del plugin_prefs['options']

    def reset_dialogs(self):
        for key in dynamic.keys():
            if key.startswith('find_duplicates_') and key.endswith('_again') \
                                                  and dynamic[key] is False:
                dynamic[key] = True
        info_dialog(self, _('Done'),
                _('Confirmation dialogs have all been reset'), show=True)

    def edit_shortcuts(self):
        d = KeyboardConfigDialog(self.plugin_action.gui, self.plugin_action.action_spec[0])
        d.exec_()

    def view_prefs(self):
        d = PrefsViewerDialog(self.plugin_action.gui, PREFS_NAMESPACE)
        d.exec_()
