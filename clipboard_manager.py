import sublime
import sublime_plugin

import re
import os
from mdpopups import show_popup as popup

HISTORY, YANK = None, None

CSS = """
    .mdpopups div.highlight,
    .mdpopups pre.highlight {
        border: 2px solid var(--mdpopups-hl-border);
        padding: 0.5rem;
        margin-bottom: 0;
        font-size: 1rem;
    }
"""

def plugin_loaded():
    global HISTORY, YANK, Vsl

    HISTORY = HistoryList([sublime.get_clipboard()])
    YANK = HistoryList()

    pcsets = sublime.load_settings('Package Control.sublime-settings')
    user = os.path.join(sublime.packages_path(), 'VirtualSpace')
    installed = 'VirtualSpace' in pcsets.get('installed_packages')
    if installed:
        from VirtualSpace.VirtualSpace import VirtualSpaceListener as Vsl
    elif os.path.isdir(user):
        from VirtualSpace.VirtualSpace import VirtualSpaceListener as Vsl
    else:
        Vsl = False

# ============================================================================


def get_clip():
    """Try to deal with stubborn clipboard refusing to open."""
    clip = None
    while not clip:
        clip = sublime.get_clipboard()
    return clip


def set_clip(s):
    """Try to deal with stubborn clipboard refusing to open."""
    while not s == get_clip():
        sublime.set_clipboard(s)


def append_clipboard():
    """
    Append the contents of the clipboard to the HISTORY global.
    """
    clip = get_clip()
    HISTORY.append(clip)
    YANK.append(clip)


def update_output_panel(window, registers=False, yank=False):
    """
    Update output panel with latest history if it is visible.
    """
    panel = window.get_output_panel('clipboard_manager')
    if panel.window():
        List = YANK if yank else HISTORY
        content = List.show_registers() if registers else List.show(yank)
        panel.run_command('clipboard_manager_dummy', {'content': content})

# ============================================================================


def clipboard_display(v, args=False):
    """Display selected clipboard content in panel or popup."""

    sets = sublime.load_settings("clipboard_manager.sublime-settings")
    panel = sets.get("display_mode") == "panel"
    pup = sets.get("display_mode") == "popup"
    status = sets.get("display_mode") == "status_bar"

    # showing in status bar
    if not pup and not panel:
        if status:
            HISTORY.show_in_status_bar()
        return

    scheme = v.settings().get('color_scheme')
    syntax = v.settings().get('syntax')

    # find popup syntax, if popup is enabled
    if pup:
        syntax = ""
        loc = v.sel()[0].b
        supported = sets.get("popup_syntaxes")
        for syn in supported:
            if v.score_selector(loc, supported[syn]):
                syntax = syn
                break

    # calling a panel
    if panel and args:
        v.window().run_command('clipboard_manager_update_panel',
                                       {"args": args})
        return

    elif panel and not args:
        args = scheme, syntax, HISTORY.current_index(), HISTORY
        v.window().run_command('clipboard_manager_update_panel',
                                       {"args": args})
        return

    # showing popup instead

    if pup and args:
        List, index = args[3], args[2]
        offset = sets.get('popup_vertical_offset')
        max = sets.get('max_quick_panel_items')
        limit = len(List) if len(List) < max else max
        vis = v.visible_region()
        vis_a = v.text_to_layout(vis.a)[1]
        vis_b = v.text_to_layout(vis.b)[1]
        mod_height = (offset - 20 * limit) if offset else 0
        loc = v.layout_to_text(
            (0, int((vis_a + vis_b) / 2 - mod_height)))

        content = "```" + syntax + "\n" + List[index] + "\n```"
        popup(v, content, css=CSS, location=loc, max_width=2000)
    else:
        content = "```" + syntax + "\n" + HISTORY.current() + "\n```"
        popup(v, content, css=CSS, location=loc, max_width=2000)

# ============================================================================


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

    def current_index(self):
        if len(self) == 0:
            return None
        return self.__index

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
        "First" actually kind of means "last",since this is a FIFO stack.
        """
        self.__index = len(self) - 1
        self.status()

    def last(self):
        """
        "Last" actually kind of means "first", since this is a FIFO stack.
        """
        self.__index = 0
        self.status()

    def show_in_status_bar(self):
        copy = self.current()
        if copy:
            copy = copy.replace("\t", "\\t")
            copy = copy.replace("\n", "\\n")
            copy = copy.replace("\r", "\\r")
            sublime.status_message(
                u'Set Clipboard to "{copy}"'.format(copy=copy))
        else:
            sublime.status_message('Nothing in history')


    def status(self):
        copy = self.current()
        if copy:
            set_clip(self.current())
        else:
            sublime.status_message('Nothing in history')

# ============================================================================


class ClipboardManager(sublime_plugin.TextCommand):
    action, indent, pop, List = False, False, False, None
    yanking, yank_choice, idx = False, False, None

    def paste(self, msg='Nothing in history'):
        List = self.List
        if not len(List):
            sublime.status_message(msg)
            return
        clip = get_clip()
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
        sublime.status_message('Yank history cleared')

    def clear_history(self):
        global HISTORY
        HISTORY = HistoryList()
        sublime.status_message('Clipboard history cleared')

    def next(self):
        HISTORY.next()
        update_output_panel(self.view.window())
        clipboard_display(self.view)

    def previous(self):
        HISTORY.previous()
        update_output_panel(self.view.window())
        clipboard_display(self.view)

    def paste_next(self):
        self.paste()
        HISTORY.next()

    def paste_previous(self):
        HISTORY.previous()
        self.paste()

    def choice_panel(self, index):
        scheme = self.view.settings().get('color_scheme')
        syntax = self.view.settings().get('syntax')
        args = scheme, syntax, index, self.List
        clipboard_display(self.view, args)

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
            self.view.window(
                ).run_command('clipboard_manager_update_panel',
                              {"close": True})

        if lines:
            sublime.active_window().show_quick_panel(lines, on_done, 2, -1,
                                                     self.choice_panel)
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


class ClipboardManagerCommandMode(sublime_plugin.TextCommand):
    """Enter command mode if not active, restore previous state when exiting.

        L.command_mode = (bool, bool)
        [0] is True if this command has been activated
        [1] is the previous state of command mode
    """
    def run(self, edit):

        ClipboardManagerListener.command_mode = True
        self.view.set_status(
            "clip_man", "  Clipboard Manager: awaiting command  ")


class ClipboardManagerUpdatePanel(sublime_plugin.TextCommand):

    def run(self, edit, args=False, close=False):

        if close:
            self.view.window().destroy_output_panel('choose_and_paste')
            return

        scheme, syntax, index, List = args
        w = sublime.active_window()
        v = w.create_output_panel('choose_and_paste')
        w.run_command("show_panel", {
            "panel": "output.choose_and_paste"})
        v.settings().set('syntax', syntax)
        v.settings().set('color_scheme', scheme)

        all = sublime.Region(0, v.size())
        v.erase(edit, all)
        v.insert(edit, 0, List[index])


class ClipboardManagerRegister(sublime_plugin.TextCommand):

    def copy(self, s):
        self.view.run_command('copy')
        content = get_clip()
        HISTORY.register(s, content)
        update_output_panel(self.view.window(), True)
        sublime.active_window().status_message(
            "   Registered in " + s)

    def paste(self, s):
        if s in HISTORY.registers:
            sublime.active_window().status_message("Pasted register " + s)
            set_clip(HISTORY.register(s))
            if self.indent:
                self.view.run_command('paste_and_indent')
            else:
                self.view.run_command('paste')
        else:
            sublime.active_window().status_message("Not a valid register")

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
        msg = ('Register in registers key?', 'Paste from registers key?')

        if mode == "reset":
            HISTORY.reset_register(reset)
            return

        msg = msg[0] if mode == 'copy' else msg[1]
        sublime.active_window().status_message(msg)
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


class ClipboardManagerEdit(sublime_plugin.TextCommand):

    def ibooks():
        for i, clip in enumerate(HISTORY):
            quotes_re = re.compile(r'^“(.*?)”\s+Excerpt From:.*$', re.DOTALL)
            match = quotes_re.search(clip)
            if match:
                clip = match.group(1)
                HISTORY[i] = clip

    def run(self, edit, action="ibooks"):

        run = eval('self.' + action)
        run()

# ============================================================================


class ClipboardManagerListener(sublime_plugin.EventListener):
    just_run = False
    command_mode = False

    def on_text_command(self, view, command_name, args):

        if self.just_run:
            self.just_run = False

        elif command_name in ['copy', 'cut']:
            self.just_run = True
            view.run_command(command_name)
            if Vsl:
                Vsl.process_command(Vsl, view)
            append_clipboard()
            update_output_panel(view.window())
            return "bla"

    def on_query_context(self, view, key, operator, operand, match_all):

        if ClipboardManagerListener.command_mode:
            if key == "clip_man":
                if operator == sublime.OP_EQUAL and operand == "non_stop":
                    pass
                else:
                    ClipboardManagerListener.command_mode = False
                    view.erase_status("clip_man")
                view.window().destroy_output_panel('choose_and_paste')
                return True
            else:
                ClipboardManagerListener.command_mode = False
                view.erase_status("clip_man")
        return None


class ClipboardManagerDummy(sublime_plugin.TextCommand):
    def run(self, edit, content):
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
