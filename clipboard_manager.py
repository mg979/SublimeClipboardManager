import re

import sublime
import sublime_plugin

HISTORY, YANK = None, None


def plugin_loaded():
    global HISTORY, YANK

    HISTORY = HistoryList([sublime.get_clipboard()])
    YANK = HistoryList()


class HistoryList(list):
    """
    List type for storing the history.
    Maintains a "pointer" to the current clipboard item
    """
    registers = {}
    SIZE = 256
    __index = 0
    last_current = None

    def show(self, yank=False):
        List = 'YANK' if yank else 'CLIPBOARD'
        ret = ""
        ret += " " + List + " HISTORY (%d)\n" % len(self)
        ret += "====================%s==\n" % ("=" * len(str(len(self))))
        for i, item in enumerate(self):
            if i == self.__index:
                ret += '--> '
            else:
                ret += '    '
            item = item.replace("\t", '\\t')
            item = item.replace("\r\n", "\n")
            item = item.replace("\r", "\n")
            item = item.replace("\n", "\n" + '       > ')
            ret += u'{i:>3}. {item}\n'.format(i=str(i + 1)[-3:], item=item)
        return ret

    def show_registers(self):
        ret = ""
        ret += " CLIPBOARD REGISTERS (%d)\n" % len(self.registers.items())
        ret += "=====================%s==\n" % ("=" * len(
            str(len(self.registers.items()))))
        for key, item in self.registers.items():
            item = item.replace("\t", '\\t')
            item = item.replace("\r\n", "\n")
            item = item.replace("\r", "\n")
            item = item.replace("\n", "\n" + ' > ')
            ret += u'{key:<1}: {item}\n'.format(key=key, item=item)
        return ret

    def reset_register(self, what):
        numbers = "1234567890"
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"

        if what == "numbers":
            for n in numbers:
                self.registers[n] = ""
        elif what == "letters":
            for n in letters:
                self.registers[n] = ""
        else:
            for n in self.registers:
                self.registers[n] = ""

    def register(self, register, *args):
        if args:
            if len(args) == 1:
                copy = args[0]
            else:
                copy = "\n".join(args)
            self.registers[register] = copy
            copy = copy.replace("\t", "\\t")
            copy = copy.replace("\n", "\\n")
            copy = copy.replace("\r", "\\r")
            sublime.status_message(
                'Set Clipboard Register "{0}" to "{1}"'.format(register, copy))
        else:
            return self.registers[register]

    def append(self, item):
        """
        Appends to the history only if it isn't the current item.
        """
        if not self or self[self.__index] != item:
            self.insert(0, item)
            self.__index = 0
            if len(self) > self.SIZE:
                del self[self.SIZE:]

    def current(self):
        if len(self) == 0:
            return None
        return self[self.__index]

    def at(self, idx):
        self.__index = (idx if idx < len(self) else 0)
        self.status()

    def next(self):
        if self.__index > 0:
            self.__index -= 1
        self.status()

    def previous(self):
        if self.__index < len(self) - 1:
            self.__index += 1
        self.status()

    def first(self):
        """
        "First" actually actually of means "last",since this is a FIFO stack.
        """
        self.__index = len(self) - 1
        self.status()

    def last(self):
        """
        "Last" actually kind of means "first", since this is a FIFO stack.
        """
        self.__index = 0
        self.status()

    def status(self):
        copy = self.current()
        if copy:
            copy = copy.replace("\t", "\\t")
            copy = copy.replace("\n", "\\n")
            copy = copy.replace("\r", "\\r")
            sublime.status_message(
                u'Set Clipboard to "{copy}"'.format(copy=copy))
            # for message externalization
            ClipboardManager.Clip = (copy, self.__index + 1, len(self))
            sublime.set_clipboard(self.current())
        else:
            sublime.status_message('Nothing in history')

# ============================================================================


def clipboard_without_ibooks_quotes():
    clipboard = sublime.get_clipboard()
    quotes_re = re.compile(r'^“(.*?)”\s+Excerpt From:.*$', re.DOTALL)
    match = quotes_re.search(clipboard)
    if match:
        clipboard = match.group(1)
        sublime.set_clipboard(clipboard)
    return clipboard


def append_clipboard():
    '''
    Append the contents of the clipboard to the HISTORY global.
    '''
    clip = sublime.get_clipboard()
    HISTORY.append(clip)
    YANK.append(clip)


def update_output_panel(window, registers=False, yank=False):
    '''
    Update output panel with latest history if it is visible
    '''
    panel = window.get_output_panel('clipboard_manager')
    if panel.window():
        List = YANK if yank else HISTORY
        content = List.show_registers() if registers else List.show(yank)
        panel.run_command('clipboard_manager_dummy', {'content': content})

# ============================================================================


class ClipboardManager(sublime_plugin.TextCommand):
    action, indent, pop, List = False, False, False, None
    yanking, yank_choice, idx = False, False, None

    def register_to(self):
        self.view.set_status('clip_man', '  Register in registers key?')
        self.action = ClipboardManagerListener.action = 'copy'

    def paste_what(self):
        self.action = ClipboardManagerListener.action = 'paste'
        self.view.set_status('clip_man', '  Paste from registers key?')

    def paste(self, msg='Nothing in history'):
        List = self.List
        if not len(List):
            sublime.status_message(msg)
            return
        clip = clipboard_without_ibooks_quotes()
        if self.indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')
        if self.pop:
            List.remove(clip)
        update_output_panel(self.view.window())

    def yank(self, choice):

        if len(YANK):
            self.List = YANK
            if choice:
                self.choose_and_paste()
            elif self.idx is not None and len(YANK) - 1 >= self.idx:
                # keep yanking from where you left the quick panel
                # reducing index because the previous one has been eaten
                YANK.at(self.idx - 1)
                self.idx -= 1
                # if index goes below zero, it reached the top and must start
                # again from the bottom, if there's something left
                if self.idx < 0:
                    self.idx = None
                self.paste()
            else:
                # keep popping the bottom-most index
                YANK.first()
                self.paste()
        else:
            sublime.status_message('Nothing to yank')

    def clear_yank_list(self):
        global YANK
        YANK = HistoryList()

    def clear_history(self):
        global HISTORY
        HISTORY = HistoryList()

    def next(self):
        HISTORY.next()
        update_output_panel(self.view.window())

    def previous(self):
        HISTORY.previous()
        update_output_panel(self.view.window())

    def paste_next(self):
        HISTORY.next()
        self.paste()

    def paste_previous(self):
        HISTORY.previous()
        self.paste()

    def choose_and_paste(self, msg='Nothing in history'):
        def format(line):
            return line.replace('\n', '\\n')[:64]

        List = self.List
        if not len(List):
            sublime.status_message(msg)
            return
        lines = []
        line_map = {}
        # filter out duplicates, keeping the first instance, and format
        for i, line in enumerate(List):
            if i == List.index(line):
                line_map[len(lines)] = i
                lines.append(format(line))

        def on_done(idx):
            if idx >= 0:
                idx = line_map[idx]
                self.idx = idx
                List.at(idx)
                self.paste()

        if lines:
            sublime.active_window().show_quick_panel(lines, on_done)
        else:
            sublime.status_message(msg)

    def register(self, x):
        if self.action == 'copy':
            self.view.run_command("clipboard_manager_copy_to_register",
                                  {"register": x})
        elif self.action == 'paste':
            self.view.run_command('clipboard_manager_paste_from_register',
                                  {"register": x,
                                   "indent": self.indent})

    def run(self, edit, **kwargs):

        if 'indent' in kwargs:
            self.indent = True
            del kwargs['indent']
        else:
            self.indent = False

        if 'yank' in kwargs:
            self.yank('choose' in kwargs)
            self.pop = True
            return
        else:
            self.List = HISTORY

        if 'pop' in kwargs:
            self.pop = True
            del kwargs['pop']
        else:
            self.pop = False

        if 'register' in kwargs:
            self.register(kwargs['register'])
            return

        for arg in kwargs:
            run = eval('self.' + arg)
            run()


class ClipboardManagerRegister(sublime_plugin.TextCommand):

    def copy(self, s):
        self.view.run_command('copy')
        content = sublime.get_clipboard()
        HISTORY.register(s, content)
        update_output_panel(self.view.window(), True)
        sublime.active_window().status_message(
            "   Registered in " + s)

    def paste(self, s):
        sublime.active_window().status_message("Pasted register " + s)
        sublime.set_clipboard(HISTORY.register(s))
        if self.indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')

    def on_change(self, s):
        if not s:
            return

        s = s[0]
        chars = "abcdefghijklmnopqrstuvwxyz" + \
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"

        w = sublime.active_window()
        if s not in chars:
            w.status_message("Not a valid key.")
            w.run_command('hide_panel')
            return
        else:
            run = eval('self.' + self.mode)
            run(s)
            w.run_command('hide_panel')

    def run(self, edit, mode='copy', indent=False, reset='letters'):

        if mode == "reset":
            HISTORY.reset_register(reset)
            return

        self.indent, self.mode = indent, mode
        s = "Enter a key (0-9, a-Z):"
        sublime.active_window().show_input_panel(s, "", None, self.on_change, None)

# ============================================================================


class ClipboardManagerShow(sublime_plugin.WindowCommand):
    def run(self, yank=False):
        self.window.run_command('show_panel',
                                {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window, yank=yank)


class ClipboardManagerShowRegisters(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command('show_panel',
                                {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window, True)

# ============================================================================


class ClipboardManagerListener(sublime_plugin.EventListener):
    just_run = False

    # def on_activated(self, view):
    #     append_clipboard()

    def on_text_command(self, view, command_name, args):

        if self.just_run:
            self.just_run = False

        elif command_name in ['copy', 'cut']:
            self.just_run = True
            view.run_command(command_name)
            append_clipboard()
            update_output_panel(view.window())
            return "bla"


class ClipboardManagerDummy(sublime_plugin.TextCommand):
    def run(self, edit, content):
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
