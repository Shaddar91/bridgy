import os
import shlex
import logging
import subprocess

logger = logging.getLogger()

def run(config, commands, in_windows=False, layout=None):
    layout_cmds = None
    if layout:
        if layout not in config['tmux']['layout']:
            raise RuntimeError("Config does not define layout: %s" % layout)
        else:
            layout_cmds = config['tmux']['layout'][layout]

    with TmuxSession(commands=commands, in_windows=in_windows, layout_cmds=layout_cmds) as tmux:
        tmux.attach()


# adapted from https://github.com/spappier/tmuxssh/
class TmuxSession(object):

    def __init__(self, session_name=None, commands=None, in_windows=False, layout_cmds=None):
        self._session_name = session_name or 'tmux-{}'.format(os.getpid())
        self._commands = commands
        self._in_windows = in_windows
        self._layout_cmds = layout_cmds
        self._created_session = False
        self._show_errors = True

    def __enter__(self):
        if len(self._commands) == 0:
            return self

        # open a set of windows and run some commands
        if self._layout_cmds:
            for cmdIdx, (name, command) in enumerate(self._commands.items()):

                if cmdIdx == 0:
                    self.new_session(self._session_name, window_name=name, command=command)
                else:
                    # new window for all layout panes running the same cmd
                    self.new_window(name, command)

                # create each pane
                for idx, item in enumerate(self._layout_cmds):

                    cmd = shlex.split(item['cmd']) + ['-t', name] + shlex.split(command)
                    if 'run' in item:
                        cmd += shlex.split(item['run'])

                    self.tmux(*cmd)

                    # get rid of the first pane as this is not running a cmd
                    if idx == 0:
                        self.kill_pane(0)

                    self.select_layout('tiled')

        # open one window
        else:
            for cmdIdx, (name, command) in enumerate(self._commands.items()):
                if self._in_windows:
                    if cmdIdx == 0:
                        self.new_session(self._session_name, window_name=name, command=command)
                    else:
                        # new window for all layout panes running the same cmd
                        self.new_window(name, command)
                else:
                    if cmdIdx == 0:
                        self.new_session(self._session_name, window_name='remote-session', command=command)
                    else:
                        self.split_window(command)

                self.select_layout('tiled')

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.kill_session()

    def suppress_errors(func):
        def wrapper(self, *args, **kwargs):
            if self._created_session:
                old_show_errors = self._show_errors
                self._show_errors = False
                ret = func(self, *args, **kwargs)
                self._show_errors = old_show_errors
                return ret
        return wrapper

    def run_only_with_session(func):
        def wrapper(self, *args, **kwargs):
            if self._created_session:
                return func(self, *args, **kwargs)
        return wrapper

    def tmux(self, *args):
        cmd = ['tmux'] + list(args)
        pipes = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        std_out, std_err = pipes.communicate()

        if pipes.returncode != 0 and self._show_errors:
            logger.error("Tmux failed (rc:%d): %s" % (pipes.returncode, " ".join(cmd)))

        elif len(std_err) and self._show_errors:
            logger.error("Tmux error: %s" % std_err)

        return std_out

    def new_session(self, session_name, window_name=None, command=None):
        cmd = ['new-session', '-ds', session_name]
        if window_name:
            cmd += ['-n', window_name]
        if command:
            cmd += shlex.split(command)

        self.tmux(*cmd)
        self._created_session = True

    @run_only_with_session
    def new_window(self, name, command):
        if command:
            self.tmux('new-window', '-n', name, *shlex.split(command))
        else:
            self.tmux('new-window', '-n', name)

    @run_only_with_session
    def split_window(self, command):
        self.tmux('split-window', '-t', self._session_name, *shlex.split(command))

    @run_only_with_session
    def select_layout(self, layout):
        self.tmux('select-layout', '-t', self._session_name, layout)

    @run_only_with_session
    def attach(self):
        self.tmux('attach', '-t', self._session_name)

    @run_only_with_session
    def set_window_option(self, option, value):
        self.tmux('set-window-option', '-t', self._session_name, option, value)

    @run_only_with_session
    def kill_pane(self, n):
        self.tmux('kill-pane', '-t', str(n))

    @run_only_with_session
    def kill_pane(self, n):
        self.tmux('kill-pane', '-t', str(n))

    @suppress_errors
    @run_only_with_session
    def kill_session(self):
        self.tmux('kill-session', '-t', self._session_name)
        self._created_session = False
