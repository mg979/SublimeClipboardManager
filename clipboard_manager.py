import re

import sublime
import sublime_plugin


class HistoryList(list):
    """
    List type for storing the history.
    Maintains a "pointer" to the current clipboard item
    """
    registers = {}
    SIZE = 256
    __index = 0

    def show(self):
        ret = ""
        ret += " CLIPBOARD HISTORY (%d)\n" % len(self)
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
        ret += "=====================%s==\n" % ("=" * len(str(len(self.registers.items()))))
        for key, item in self.registers.items():
            item = item.replace("\t", '\\t')
            item = item.replace("\r\n", "\n")
            item = item.replace("\r", "\n")
            item = item.replace("\n", "\n" + ' > ')
            ret += u'{key:<1}: {item}\n'.format(key=key, item=item)
        return ret

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
            sublime.status_message('Set Clipboard Register "{0}" to "{1}"'.format(register, copy))
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
        """"first" actually kind of means "last", since this is a FIFO stack"""
        self.__index = len(self) - 1
        self.status()

    def last(self):
        """"last" actually kind of means "first", since this is a FIFO stack"""
        self.__index = 0
        self.status()

    def status(self):
        copy = self.current()
        copy = copy.replace("\t", "\\t")
        copy = copy.replace("\n", "\\n")
        copy = copy.replace("\r", "\\r")
        sublime.status_message(u'Set Clipboard to "{copy}"'.format(copy=copy))
        sublime.set_clipboard(self.current())


HISTORY = HistoryList([sublime.get_clipboard()])


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
    HISTORY.append(clipboard_without_ibooks_quotes())


def update_output_panel(window, registers=False):
    '''
    Update output panel with latest history if it is visible
    '''
    panel = window.get_output_panel('clipboard_manager')
    if panel.window():
        content = HISTORY.show_registers() if registers else HISTORY.show()
        panel.run_command('clipboard_manager_dummy', {'content': content })


class ClipboardManagerPaste(sublime_plugin.TextCommand):
    def run(self, edit, indent=False):
        clipboard_without_ibooks_quotes()
        if indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')


class ClipboardManagerCut(sublime_plugin.TextCommand):
    def run(self, edit):
        '''
        First run sublime's command to extract the selected text. This will set
        the cut/copy'd data on the clipboard which we can easily steal without
        recreating the cut/copy logic.
        '''
        self.view.run_command('cut')
        append_clipboard()
        update_output_panel(self.view.window())


class ClipboardManagerCopy(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.run_command('copy')
        append_clipboard()
        update_output_panel(self.view.window())


class ClipboardManagerCopyToRegister(sublime_plugin.TextCommand):
    def run(self, edit, register=None, content=None):
        if register:
            self.view.run_command('copy')
            if content is None:
                content = sublime.get_clipboard()
            HISTORY.register(register, content)
            update_output_panel(self.view.window(), True)
        else:
            self.view.run_command('copy')
            content = sublime.get_clipboard()
            chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
            lines = list(chars)
            def on_done(idx):
                self.view.window().run_command('clipboard_manager_copy_to_register', {'register': lines[idx], 'content': content})
            sublime.active_window().show_quick_panel(lines, on_done)


class ClipboardManagerPasteFromRegister(sublime_plugin.TextCommand):
    def run(self, edit, register):
        sublime.set_clipboard(HISTORY.register(register))
        self.view.run_command('paste')


class ClipboardManagerNext(sublime_plugin.TextCommand):
    def run(self, edit):
        HISTORY.next()
        update_output_panel(self.view.window())


class ClipboardManagerNextAndPaste(sublime_plugin.TextCommand):
    def run(self, edit, indent=False):
        HISTORY.next()
        if indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')
        update_output_panel(self.view.window())


class ClipboardManagerPrevious(sublime_plugin.TextCommand):
    def run(self, edit):
        HISTORY.previous()
        update_output_panel(self.view.window())


class ClipboardManagerPreviousAndPaste(sublime_plugin.TextCommand):
    def run(self, edit, indent=False):
        HISTORY.previous()
        if indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')
        update_output_panel(self.view.window())


class ClipboardManagerShow(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command('show_panel', {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window)


class ClipboardManagerShowRegisters(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command('show_panel', {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window, True)


class ClipboardManagerChooseAndPaste(sublime_plugin.TextCommand):
    def run(self, edit):
        def format(line):
            return line.replace('\n', '\\n')[:64]

        lines = []
        line_map = {}
        # filter out duplicates, keeping the first instance, and format
        for i, line in enumerate(HISTORY):
            if i == HISTORY.index(line):
                line_map[len(lines)] = i
                lines.append(format(line))

        def on_done(idx):
            if idx >= 0:
                idx = line_map[idx]
                HISTORY.at(idx)
                self.view.run_command('paste')

        if lines:
            sublime.active_window().show_quick_panel(lines, on_done)
        else:
            sublime.status_message('Nothing in history')


class ClipboardManagerEventListener(sublime_plugin.EventListener):
    def on_activated(self, view):
        append_clipboard()


class ClipboardManagerDummy(sublime_plugin.TextCommand):
    def run(self, edit, content):
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
