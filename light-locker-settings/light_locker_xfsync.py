#!/usr/bin/python
# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
#   Light Locker Settings - simple configuration tool for light-locker
#   Copyright (C) 2014 Thomas Molloy <beetyrootey@gmail.com>
#
#   This program is free software: you can redistribute it and/or modify it
#   under the terms of the GNU General Public License version 3, as published
#   by the Free Software Foundation.
#
#   This program is distributed in the hope that it will be useful, but
#   WITHOUT ANY WARRANTY; without even the implied warranties of
#   MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
#   PURPOSE.  See the GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License along
#   with this program.  If not, see <http://www.gnu.org/licenses/>.

import subprocess


def convert_value(value):
    """Make output agreeable to xfconf."""
    if isinstance(value, bool):
        if value is True:
            value = 'true'
        else:
            value = 'false'
    return value


def xfconf_init_property(channel, p_name, p_type, initial_value):
    """Initialize the specified xfconf property."""
    p_type = p_type.__name__
    initial_value = str(convert_value(initial_value))
    cmd = 'xfconf-query -c %s -p %s -n -s %s -t %s' % (channel, p_name,
                                                       initial_value, p_type)
    subprocess.call(cmd.split())


def xfconf_list_properties(channel):
    """List the properties defined for the given channel."""
    settings = dict()
    cmd = 'xfconf-query -c %s -l -v' % channel
    output = subprocess.check_output(cmd, shell=True)
    if not isinstance(output, str):
        output = output.decode('utf-8')
    for line in output.split('\n'):
        try:
            key, value = line.split(None, 1)
        except ValueError:
            key = line.strip()
            value = ""
        if str.isdigit(value):
            value = int(value)
        elif value.lower() in ['true', 'false']:
            value = value.lower() == 'true'
        else:
            value = str(value)
        settings[key] = value
    return settings


def xfconf_set_property(channel, prop, value):
    """Set the specified xfconf property."""
    value = str(value).lower()
    cmd = 'xfconf-query -c %s -p %s -s %s' % (channel, prop, value)
    subprocess.call(cmd.split())


class XfceSessionSync():
    """
    Class to set/get xfce4-session lock settings.
    """
    def __init__(self):
        """Initialize the XfceSessionSync instance."""
        self.settings = {'/shutdown/LockScreen': False}
        current_settings = self._get_xfce4_session_settings()
        self._update_settings(current_settings)
        self._init_xfconf_properties(current_settings)

    def _init_xfconf_properties(self, current_settings):
        """If xfce4-session has not been configured, some of its properties
        may not exist. Create any missing properties."""
        channel = 'xfce4-session'
        for key, value in list(self.settings.items()):
            if key not in list(current_settings.keys()):
                xfconf_init_property(channel, key, type(value), value)

    def _get_xfce4_session_settings(self):
        """Return a dictionary of the xfce4-session settings."""
        return xfconf_list_properties('xfce4-session')

    def _update_settings(self, settings):
        """Update the internal settings."""
        for key, value in list(settings.items()):
            if key in list(self.settings.keys()):
                self.settings[key] = value

    def get_lock(self):
        """Return True if Lock on Sleep is enabled."""
        return self.settings['/shutdown/LockScreen']

    def set_lock(self, value):
        """Set the Lock on Sleep setting."""
        xfconf_set_property('xfce4-session', '/shutdown/LockScreen', value)
        self.settings['/shutdown/LockScreen'] = value


class XfpmSync():
    """
    Class to set/get xserver dpms timings via xfpm, thus keeping xfpm in sync.
    """
    def __init__(self):
        '''Following settings should concur with xfpm defaults'''
        self.settings = {'/xfce4-power-manager/lock-screen-suspend-hibernate':
                         False,
                         '/xfce4-power-manager/logind-handle-lid-switch': True
                         }
        current_settings = self._get_xfpm_settings()
        self._update_settings(current_settings)
        self._init_xfconf_properties(current_settings)

    def _init_xfconf_properties(self, current_settings):
        """
        If xfpm has never been used, some xfconf channel properties may not be
        set. Ensures that we don't get complains about missing properties.
        """
        channel = 'xfce4-power-manager'
        for key, value in list(self.settings.items()):
            if key not in list(current_settings.keys()):
                xfconf_init_property(channel, key, type(value), value)

    def _get_xfpm_settings(self):
        """Returns xfpm xfconf settings as string"""
        return xfconf_list_properties('xfce4-power-manager')

    def _update_settings(self, settings):
        """Update the internal settings."""
        for key, value in list(settings.items()):
            if key in list(self.settings.keys()):
                self.settings[key] = value

    def get_lock(self):
        """Return True if Lock on Suspend/Hibernate is enabled."""
        prop_name = '/xfce4-power-manager/lock-screen-suspend-hibernate'
        return self.settings[prop_name]

    def set_lock(self, value):
        """Set the Lock on Suspend/Hibernate setting."""
        prop_name = '/xfce4-power-manager/lock-screen-suspend-hibernate'
        xfconf_set_property('xfce4-power-manager', prop_name, value)
        self.settings[prop_name] = value

        # The below setting is required to avoid the dreaded "black screen bug"
        # where the session does not properly suspend after hibernation.
        # If this setting is True, logind will handle the lid-switch event.
        # This setting should be True when lock on suspend is enabled.
        prop_name = '/xfce4-power-manager/logind-handle-lid-switch'
        xfconf_set_property('xfce4-power-manager', prop_name, value)
        self.settings[prop_name] = value
