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

import gettext
gettext.textdomain('light-locker-settings')

from gettext import gettext as _
from gettext import ngettext

import re
import argparse
import shlex
import os
import subprocess
from gi.repository import Gtk, GLib, Gio

import psutil
old_psutil_format = isinstance(psutil.Process.username, property)

import light_locker_xfsync

''' Settings window for the light-locker '''

username = GLib.get_user_name()


screensaver_managers = {
    'xfce4-power-manager': (_("Xfce Power Manager"), "xfce4-power-manager -c")
}


class LightLockerSettings:
    '''Light Locker Settings application class.'''

    def __init__(self):
        '''Initialize the Light Locker Settings application.'''
        self.light_locker_keyfile = None
        self.screensaver_keyfile = None

        self.builder = Gtk.Builder()
        self.builder.set_translation_domain ('light-locker-settings')

        script_dir = os.path.dirname(os.path.abspath(__file__))
        glade_file = os.path.join(script_dir, "light-locker-settings.glade")
        self.builder.add_from_file(glade_file)
        self.builder.connect_signals(self)

        self.window = self.builder.get_object("light_locker_settings_window")
        self.window.set_title(_("Light Locker Settings"))

        ''' Set background-color of frame to base-color to make it resemble the
        XfceHeading widget '''
        self.xfce_header = self.builder.get_object("xfce_header")
        entry = Gtk.Entry.new()
        style = entry.get_style_context()
        base_color = style.lookup_color("theme_base_color")
        self.xfce_header.override_background_color(0, base_color[1])
        fg_color = style.lookup_color("theme_fg_color")
        self.xfce_header.override_color(0, fg_color[1])

        self.use_lightlocker = self.builder.get_object("use_lightlocker")
        self.session_lock_combo = self.builder.get_object("session_lock_combo")
        self.lock_on_suspend = self.builder.get_object("lock_on_suspend")

        self.apply = self.builder.get_object("apply")

        ''' Set up scales '''
        self.screenblank_timeout = self.builder.get_object(
            "screenblank_timeout")
        self.screenblank_timeout.add_mark(1, 3, None)
        self.screenoff_timeout = self.builder.get_object("screenoff_timeout")
        self.screenoff_timeout.add_mark(1, 3, None)
        self.lock_delay = self.builder.get_object("lock_delay")
        self.lock_delay.add_mark(0, 3, None)
        for i in range(1, 13):
            self.screenblank_timeout.add_mark(i * 10, 3, None)
            self.screenoff_timeout.add_mark(i * 10, 3, None)
            self.lock_delay.add_mark(i * 10, 3, None)

        self.screensaver_managed = False

        self.gsettings_init()

        self.init_settings()

        ''' Monitor changes to the settings '''
        self.apply.set_sensitive(False)
        self.locksettings_changed = False
        self.screenblank_timeout.connect(
            "value-changed", self.screenblank_value_changed_cb)
        self.screenoff_timeout.connect(
            "value-changed", self.screenoff_value_changed_cb)
        self.lock_delay.connect(
            "value-changed", self.lock_delay_value_changed_cb)

        self.window.show()

# Application Callbacks
    def screenblank_value_changed_cb(self, gparam):
        '''Sync screenblank and screenoff settings when values are modified.'''
        self.apply.set_sensitive(True)

        blank_timeout = int(self.screenblank_timeout.get_value())
        off_timeout = int(self.screenoff_timeout.get_value())

        ''' screenoff can never be shorter than screenblank-timeout '''
        if (blank_timeout >= off_timeout) and (off_timeout != 0):
            self.screenoff_timeout.set_value(blank_timeout)

    def screenoff_value_changed_cb(self, gparam):
        '''Sync screenblank and screenoff settings when values are modified.'''
        self.apply.set_sensitive(True)

        blank_timeout = int(self.screenblank_timeout.get_value())
        off_timeout = int(self.screenoff_timeout.get_value())

        ''' screenoff can never be shorter than screenblank-timeout '''
        if off_timeout <= blank_timeout:
            self.screenblank_timeout.set_value(off_timeout)

    def use_lightlocker_cb(self, switch, gparam):
        '''Update the displayed lock controls when light-locker is enabled or
        disabled.'''
        ''' if on then allow for the timeout to be set '''
        self.locksettings_changed = True
        self.apply.set_sensitive(True)
        if switch.get_active():
            self.lock_delay.set_sensitive(False)
            self.session_lock_combo.set_sensitive(False)
            self.lock_on_suspend.set_sensitive(False)
        else:
            self.session_lock_combo.set_sensitive(True)
            self.lock_on_suspend.set_sensitive(True)
            if self.session_lock_combo.get_active() != 2:
                self.lock_delay.set_sensitive(True)

    def on_session_lock_combo_changed(self, widget):
        '''Update the displayed screen blanking controls when locking is
        enabled or disabled.'''
        self.locksettings_changed = True
        self.apply.set_sensitive(True)

        # Check the session lock combo:
        #  0. lock when screensaver is activated
        #  1. lock when screensaver is deactivated
        #  2. never lock
        active = widget.get_active()
        self.lock_delay.set_sensitive(active != 2)

    def lock_delay_value_changed_cb(self, gparam):
        '''Enable saving of lock setting when the delay has been modified.'''
        self.locksettings_changed = True
        self.apply.set_sensitive(True)

    def lock_on_suspend_cb(self, widget, gparam):
        '''Enable saving when locking on suspend is changed.'''
        self.locksettings_changed = True
        self.apply.set_sensitive(True)

    def apply_cb(self, button, data=None):
        '''Apply changes and update the relevant setting files.'''
        self.apply_settings()
        self.apply.set_sensitive(False)

    def on_window_destroy(self, *args):
        '''Exit the application when the window is closed.'''
        Gtk.main_quit()

    def on_close_clicked(self, *args):
        '''Exit the application when the window is closed.'''
        Gtk.main_quit()

# Process Management
    def get_process_username(self, process):
        """Return the username of the process owner."""
        p_user = None

        try:
            if old_psutil_format:
                p_user = process.username
            else:
                p_user = process.username()
        except:
            pass

        return p_user

    def get_process_name(self, process):
        """Return the name of the running process."""
        p_name = None

        try:
            if old_psutil_format:
                p_name = os.path.basename(process.exe)
            else:
                p_name = os.path.basename(process.exe())
        except:
            pass

        return p_name

    def check_running_process(self, process_name):
        """Return True if the specified process is active."""
        # Find the process...
        for pid in psutil.get_pid_list():
            try:
                p = psutil.Process(pid)
                if self.get_process_username(p) == username:
                    # Return True if the process is found.
                    if self.get_process_name(p) == process_name:
                        return True
            except:
                pass

        return False

    def stop_light_locker(self):
        """Safely stop the light-locker process."""
        # Find the process...
        for pid in psutil.get_pid_list():
            try:
                p = psutil.Process(pid)
                if self.get_process_username(p) == username:
                    # When found, end the light-locker process.
                    if self.get_process_name(p) == 'light-locker':
                        p.terminate()
            except:
                pass

    def run_command(self, cmd, check_output=False):
        '''Run a shell command, return its output.'''
        if len(cmd) == 0:
            return None
        if check_output:
            output = subprocess.check_output(cmd, shell=True)
            if not isinstance(output, str):
                output = output.decode('utf-8')
            return output
        else:
            subprocess.Popen(cmd.split(" "))
            return None

    def run_command_cb(self, widget, cmd):
        self.run_command(cmd, False)

# Light Locker 1.5.1
    def gsettings_init(self):
        self.gsettings = None
        schema_source = Gio.SettingsSchemaSource.get_default()
        if (schema_source.lookup('apps.light-locker', False)):
            self.gsettings = Gio.Settings.new('apps.light-locker')

    def gsettings_available(self):
        return self.gsettings is not None

    def gsettings_get_settings(self):
        lock_after_screensaver = self.gsettings.get_uint('lock-after-screensaver')
        late_locking = self.gsettings.get_boolean('late-locking')
        lock_on_suspend = self.gsettings.get_boolean('lock-on-suspend')

        settings = dict()
        settings['light-locker-enabled'] = self.get_light_locker_enabled()
        settings['lock-after-screensaver'] = lock_after_screensaver > 0
        settings['late-locking'] = late_locking
        settings['lock-on-suspend'] = lock_on_suspend
        settings['lock-time'] = \
            self.light_locker_time_down_scaler(lock_after_screensaver)

        return settings

    def gsettings_set_enabled(self, enable):
        if enable:
            light_locker_exec = "light-locker"
        else:
            light_locker_exec = ""
        keyfile = self.get_light_locker_autostart()
        keyfile.set_value("Desktop Entry", "Exec", light_locker_exec)
        self.save_light_locker_autostart()

    def gsettings_set_late_locking(self, enable):
        self.gsettings.set_boolean("late-locking", enable)

    def gsettings_set_lock_after_screensaver(self, value):
        self.gsettings.set_uint("lock-after-screensaver", value)

    def gsettings_set_lock_on_suspend(self, enable):
        self.gsettings.set_boolean("lock-on-suspend", enable)

# Key Files
    def ll_keyfile_get_settings(self):
        # Defaults
        settings = {
            'light-locker-enabled': False,
            'lock-after-screensaver': False,
            'late-locking': False,
            'lock-on-suspend': False,
            'lock-time': 10
        }

        keyfile = self.get_light_locker_autostart()
        if self.get_light_locker_enabled():
            settings['light-locker-enabled'] = True

            ll_exec = keyfile.get_value("Desktop Entry", "Exec");
            value = ll_exec.replace("=", " ")
            splitArgs = shlex.split(value)

            parser = argparse.ArgumentParser(
                description='Light Locker Settings')
            parser.add_argument("--lock-after-screensaver")
            parser.add_argument("--late-locking", action='store_true')
            parser.add_argument("--lock-on-suspend", action='store_true')
            (args, others) = parser.parse_known_args(splitArgs)

            # Lock after screensaver
            if args.lock_after_screensaver:
                if int(args.lock_after_screensaver) != 0:
                    settings['lock-after-screensaver'] = True
                    settings['lock-time'] = self.light_locker_time_down_scaler(
                        int(args.lock_after_screensaver))

            # Late Locking
            if args.late_locking:
                settings['late-locking'] = True

            # Lock on Suspend
            if args.lock_on_suspend:
                settings['lock-on-suspend'] = True

        return settings

    def get_autostart(self, filename, defaults={}):
        autostart = os.path.join(GLib.get_user_config_dir(), 'autostart')
        if not os.path.exists(autostart):
            os.makedirs(autostart)
        keyfile = GLib.KeyFile.new()

        dirs = []
        dirs.append (autostart)
        for directory in (GLib.get_system_config_dirs()):
            dirs.append (os.path.join(directory, 'autostart'))

        keyfile.load_from_dirs(filename, dirs,
                               GLib.KeyFileFlags.KEEP_TRANSLATIONS)

        for key in defaults.keys():
            try:
                if keyfile.get_value("Desktop Entry", key) is None:
                    keyfile.set_value("Desktop Entry", key, defaults[key])
            except GLib.Error:
                keyfile.set_value("Desktop Entry", key, defaults[key])

        return keyfile

    def get_light_locker_autostart(self):
        if self.light_locker_keyfile is not None:
            return self.light_locker_keyfile

        defaults = {
            "Type": "Application",
            "Name": _("Screen Locker"),
            "Comment": _("Launch screen locker program"),
            "Icon": "preferences-desktop-screensaver",
            "NoDisplay": "true",
            "NotShownIn": "Gnome;Unity",
            "Exec": ""
        }

        self.light_locker_keyfile = \
            self.get_autostart('light-locker.desktop', defaults)

        return self.light_locker_keyfile

    def get_screensaver_autostart(self):
        if self.screensaver_keyfile is not None:
            return self.screensaver_keyfile

        defaults = {
            "Type": "Application",
            "Name": _("Screensaver"),
            "Comment": _("Set screensaver timeouts"),
            "Exec": ""
        }

        self.screensaver_keyfile = \
            self.get_autostart('screensaver-settings.desktop', defaults)
        return self.screensaver_keyfile

    def save_light_locker_autostart(self):
        filename = os.path.join(GLib.get_user_config_dir(), 'autostart',
                                'light-locker.desktop')
        autostart = self.get_light_locker_autostart()
        autostart.save_to_file(filename)

    def save_screensaver_autostart(self):
        filename = os.path.join(GLib.get_user_config_dir(), 'autostart',
                                'screensaver-settings.desktop')
        autostart = self.get_screensaver_autostart()
        autostart.save_to_file(filename)

# Settings Parsing
    def use_screensaver_manager(self, name, command):
        """Replace the Screensaver settings with a different application."""
        self.screensaver_managed = True

        infobar = self.builder.get_object("screensaver_info")
        infobar_label = self.builder.get_object("screensaver_info_label")
        infobar_button = self.builder.get_object("screensaver_info_button")
        screensaver_frame = self.builder.get_object("screensaver_details")

        # Light Locker Settings is *NOT* controlling the screensaver.
        filename = os.path.join(GLib.get_user_config_dir(), 'autostart',
                                'screensaver-settings.desktop')
        if os.path.isfile(filename):
            os.remove(filename)
        screensaver_frame.hide()

        # Update the InfoBar
        infobar_label.set_label(
            _("Your screensaver settings are managed by %s.") % name)
        infobar_button.connect("clicked", self.run_command_cb, command)
        infobar.show()

    def init_settings(self):
        if self.gsettings_available():
            settings = self.gsettings_get_settings()
            ll_exec_settings = self.ll_keyfile_get_settings()
            if ll_exec_settings['lock-after-screensaver']:
                settings['lock-after-screensaver'] = True
            if ll_exec_settings['late-locking']:
                settings['late-locking'] = True
            if ll_exec_settings['lock-on-suspend']:
                settings['lock-on-suspend'] = True
            if ll_exec_settings['lock-time'] != 10:
                settings['lock-time'] = ll_exec_settings['lock-time']
        else:
            settings = self.ll_keyfile_get_settings()

        # Replace settings with xfce4-power-manager
        if self.check_running_process("xfce4-power-manager"):
            xfpm_sync = light_locker_xfsync.XfpmSync()
            settings['lock-on-suspend'] = xfpm_sync.get_lock()

        # Check if any known screensaver managers are currently running.
        for process_name in screensaver_managers.keys():
            if self.check_running_process(process_name):
                name, command = screensaver_managers[process_name]
                self.use_screensaver_manager(name, command)
                break

        # Extract the settings
        use_light_locker = settings['light-locker-enabled']
        lock_after_screensaver = settings['lock-after-screensaver']
        late_locking = settings['late-locking']
        lock_on_suspend = settings['lock-on-suspend']
        lock_time = settings['lock-time']
        screen_blank_timeout, screen_off_timeout = \
            self.get_screen_blank_timeout()

        # Apply the settings
        self.use_lightlocker.set_active(use_light_locker)
        self.session_lock_combo.set_sensitive(use_light_locker)
        self.lock_on_suspend.set_sensitive(use_light_locker)

        self.lock_delay.set_value(lock_time)

        if lock_after_screensaver:
            self.lock_delay.set_sensitive(True)
            if late_locking:
                self.session_lock_combo.set_active(1)
            else:
                self.session_lock_combo.set_active(0)
        else:
            self.lock_delay.set_sensitive(False)
            self.session_lock_combo.set_active(2)

        self.lock_on_suspend.set_active(lock_on_suspend)

        blank = self.light_locker_time_down_scaler(screen_blank_timeout)
        off = self.light_locker_time_down_scaler(screen_off_timeout)
        self.screenblank_timeout.set_value(blank)
        self.screenoff_timeout.set_value(off)

    def get_light_locker_enabled(self):
        keyfile = self.get_light_locker_autostart()
        ll_exec = keyfile.get_value("Desktop Entry", "Exec")
        return "light-locker" in ll_exec

    def get_screen_blank_timeout(self):
        ''' read in the X11 screensaver settings from bash '''
        # Defaults
        screen_blank = 10
        screen_off = 15

        # Get the xset output to parse.
        screensaver_output = self.run_command('xset q', check_output=True)

        # Get the Screen-Blank timeout
        screenblank_timeout_grep = re.search(
            "timeout: *(\d+)", screensaver_output)
        if screenblank_timeout_grep:
            screenblank_timeout = re.findall(
                '\d+', screenblank_timeout_grep.group(1))
            screen_blank = int(screenblank_timeout[0]) / 60

        # Get the Screen-Off timeout
        screenoff_timeout_grep = re.search(
            "Standby: *(\d+)", screensaver_output)
        if screenoff_timeout_grep:
            screenoff_timeout = re.findall(
                '\d+', screenoff_timeout_grep.group(1))
            screen_off = int(screenoff_timeout[0]) / 60

        # Return the current timeout settings
        return screen_blank, screen_off

# Label Formatters
    def screensaver_label_formatter(self, screenblank_timeout, max_value):
        '''Convert timeout values to a more friendly format.'''
        value = int(screenblank_timeout.get_value())
        if value == 0:
            return _("Never")
        else:
            return ngettext("%d minute", "%d minutes", value) % (value,)

    def light_locker_label_formatter(self, light_locker_slider, max_value):
        '''Convert timeout values to a more friendly format.'''
        value = int(light_locker_slider.get_value())
        if value == 0:
            formatted_string = _("Never")
        else:
            value = self.light_locker_time_up_scaler(value)
            formatted_string = self.secs_to_readable(value)
        return formatted_string

    def secs_to_readable(self, seconds):
        '''Convert seconds to a more friendly format.'''
        if seconds >= 60:
            minutes = seconds / 60
            return ngettext("%d minute", "%d minutes", minutes) % (minutes,)
        else:
            return ngettext("%d second", "%d seconds", seconds) % (seconds,)

# Time Scalers
    def light_locker_time_up_scaler(self, time):
        '''Scale times up.'''
        if time > 60:
            time = (time - 60) * 60
        return time

    def light_locker_time_down_scaler(self, time):
        '''Scale times down.'''
        if time > 60:
            time = time / 60 + 60
        return time

# Settings Writing
    def get_updated_settings(self):
        """Return a dictionary with the updated settings from the GUI."""
        # Get the lock-after-screensaver timeout.
        session_lock = self.session_lock_combo.get_active()
        if session_lock == 2:  # never lock with screensaver
            late_locking = False
            lock_delay = 0
        else:
            if session_lock == 0:  # lock when screensaver is activated
                late_locking = False
            if session_lock == 1:  # lock when screensaver is deactivated
                late_locking = True
            lock_delay = self.light_locker_time_up_scaler(
                int(self.lock_delay.get_value()))

        # Lock Enabled?
        lock_enabled = self.use_lightlocker.get_active()

        # Get the suspend setting.
        lock_on_suspend = self.lock_on_suspend.get_active()

        # Get the screen-blank and screen-off timeout.
        screenblank_timeout = \
            int(self.screenblank_timeout.get_value()) * 60
        screenoff_timeout = int(self.screenoff_timeout.get_value()) * 60

        settings = {
            "lock-enabled": lock_enabled,
            "late-locking": late_locking,
            "lock-after-screensaver": lock_delay,
            "lock-on-suspend": lock_on_suspend,
            "screen-blank-timeout": screenblank_timeout,
            "screen-off-timeout": screenoff_timeout
        }

        return settings

    def apply_settings(self):
        """Apply updated settings."""
        # Get the current settings from the GUI.
        settings = self.get_updated_settings()
        lock_on_suspend = settings['lock-on-suspend']

        # If xfce4-sesssion is running, sync the lock-on-suspend setting.
        if self.check_running_process("xfce4-session"):
            session_sync = light_locker_xfsync.XfceSessionSync()
            session_sync.set_lock(lock_on_suspend)

        # If xfpm manages locking, disable it for light-locker.
        if self.check_running_process("xfce4-power-manager"):
            xfpm_sync = light_locker_xfsync.XfpmSync()
            xfpm_sync.set_lock(lock_on_suspend)

        # Apply the remaining settings to light-locker.
        self.apply_light_locker_settings(settings)

        if not self.screensaver_managed:
            self.apply_screen_blank_settings(settings)

    def apply_light_locker_settings(self, settings):
        '''Apply the light-locker settings'''
        lock_enabled = settings['lock-enabled']
        late_locking = settings['late-locking']
        lock_on_suspend = settings['lock-on-suspend']
        lock_after_screensaver = settings['lock-after-screensaver']

        # If GSettings is available, prefer the following method.
        if self.gsettings_available():
            self.gsettings_set_enabled(lock_enabled)
            self.gsettings_set_late_locking(late_locking)
            self.gsettings_set_lock_after_screensaver(lock_after_screensaver)
            self.gsettings_set_lock_on_suspend(lock_on_suspend)
            return

        # Else, proceed with the legacy code below
        # Stop any running light-locker processes.
        self.stop_light_locker()

        if late_locking:
            late_locking = "--late-locking"
        else:
            late_locking = "--no-late-locking"

        if lock_on_suspend:
            lock_on_suspend = "--lock-on-suspend"
        else:
            lock_on_suspend = "--no-lock-on-suspend"

        lock_after_screensaver = "--lock-after-screensaver=%i" % \
            lock_after_screensaver

        # Build the light-locker command.
        light_locker_exec = ""
        if lock_enabled:
            light_locker_exec = \
                "light-locker %s %s %s" % (lock_after_screensaver,
                                           lock_on_suspend, late_locking)

        # Save the light-locker autostart file.
        keyfile = self.get_light_locker_autostart()
        keyfile.set_value("Desktop Entry", "Exec", light_locker_exec)
        self.save_light_locker_autostart()

        # Execute the updated light-locker command.
        self.run_command(light_locker_exec)

    def apply_screen_blank_settings(self, settings):
        '''Apply the screen blank settings.'''
        screenblank_timeout = settings['screen-blank-timeout']
        screenoff_timeout = settings['screen-off-timeout']

        # Build the screen-blank/off command.
        screensaver_exec = \
            "xset s %i dpms %i 0 0" % (screenblank_timeout, screenoff_timeout)

        # Execute the updated screensaver command.
        self.run_command(screensaver_exec)

        # Save the screensaver autostart file.
        keyfile = self.get_screensaver_autostart()
        keyfile.set_value("Desktop Entry", "Exec", screensaver_exec)
        self.save_screensaver_autostart()


if __name__ == "__main__":
    main = LightLockerSettings()
    Gtk.main()
