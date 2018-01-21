"""Sublime Clipboard Manager."""
import sublime
import sublime_plugin
import re
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
    """On restart."""
    global HISTORY, YANK, YANK_MODE, Vsl, sets, explicit_yank_mode

    sets = sublime.load_settings("clipboard_manager.sublime-settings")

    try:
        from VirtualSpace.VirtualSpace import VirtualSpaceListener as Vsl
    except ImportError:
        Vsl = False

    HISTORY = HistoryList()
    YANK = HistoryList()

    explicit_yank_mode = sets.get('explicit_yank_mode', False)
    # allow copying to yank list already, if explicit mode is off
    YANK_MODE = not explicit_yank_mode

# ============================================================================


def get_clip():
    """Try to deal with stubborn clipboard refusing to open."""
    clip = None
    while not clip:
        clip = sublime.get_clipboard()
    return clip


def set_clip(s):
    """Try to deal with stubborn clipboard refusing to open."""
    while s != get_clip():
        sublime.set_clipboard(s)


def append_clipboard():
    """Append the contents of the clipboard to the HISTORY and YANK globals."""
    clip = get_clip()
    if YANK_MODE:
        YANK.append(clip)
        # only use yank list, if explicit_yank_mode is active
        if explicit_yank_mode:
            return
    HISTORY.append(clip)


def update_output_panel(window, registers=False, yank=False):
    """Update output panel with latest history if it is visible."""
    panel = window.get_output_panel('clipboard_manager')
    if panel.window():
        List = YANK if yank else HISTORY
        content = List.show_registers() if registers else List.show(yank)
        panel.run_command('clipboard_manager_dummy', {'content': content})

# ============================================================================


def clipboard_display(v, args=False):
    """Display selected clipboard content in panel or popup."""
    mode = sets.get("display_mode")

    panel = mode == "panel"
    pup = mode == "popup"
    status = mode == "status_bar"

    # showing in status bar
    if not pup and not panel:
        if status:
            HISTORY.show_in_status_bar()
        return

    (List, index) = args if args else (HISTORY, HISTORY.current_index())
    syntax, scheme, codeblock_syn = List.clip_syntaxes[index]

    # calling a panel
    if panel:
        args = scheme, syntax, index, List
        v.window().run_command('clipboard_manager_update_panel', {"args": args})
        return

    # showing popup instead

    if pup and args:
        offset = sets.get('popup_vertical_offset')
        max = sets.get('max_quick_panel_items')
        limit = len(List) if len(List) < max else max
        vis = v.visible_region()
        vis_a = v.text_to_layout(vis.a)[1]
        vis_b = v.text_to_layout(vis.b)[1]
        mod_height = (offset - 20 * limit) if offset else 0
        loc = v.layout_to_text((0, int((vis_a + vis_b) / 2 - mod_height)))

        st = List[index]
        content = "```" + codeblock_syn + "\n" + (st[:350] + "\n...\n" if len(st) > 500 else st) + "\n```"
        popup(v, content, css=CSS, location=loc, max_width=2000)
    else:
        st = HISTORY.current()
        content = "```" + codeblock_syn + "\n" + (st[:350] + "\n...\n" if len(st) > 500 else st) + "\n```"
        popup(v, content, css=CSS, location=loc, max_width=2000)

# ============================================================================


class HistoryList(list):
    """List type for storing the history. Maintains a "pointer" to the current clipboard item."""

    registers = {}
    SIZE = 256
    __index = 0
    clip_syntaxes = []

    def show(self, yank=False):
        """Show history entries in output panel."""
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
        """Show registers in output panel."""
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
        """Reset specific register."""
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
        """Save in specific register."""
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

    def clip_syntax(self):
        """Store syntax/scheme for popup or panel display."""
        view = sublime.active_window().active_view()
        supported = sets.get("popup_syntaxes")
        codeblock_syn = ''
        for syn in supported:
            if view.score_selector(0, supported[syn]):
                codeblock_syn = syn
                break
        return (view.settings().get('syntax'), view.settings().get('color_scheme'), codeblock_syn)

    def append(self, item):
        """Append to the history, or reposition item if already present."""
        if self and item in self:
            ix = self.index(item)
            del self[ix]
            del self.clip_syntaxes[ix]

        self.insert(0, item)
        self.clip_syntaxes.insert(0, self.clip_syntax())
        self.__index = 0

        # for some reason clip_syntaxes is updated twice!? correct this insult
        if len(self.clip_syntaxes) > len(self):
            del self.clip_syntaxes[0]

        if len(self) > self.SIZE:
            del self[-1]
            del self.clip_syntaxes[-1]

    def current(self):
        """Return item at current history index."""
        return self[self.__index] if len(self) else None

    def current_index(self):
        """Return current history index."""
        return self.__index if len(self) else None

    def at(self, idx):
        """Reposition index."""
        self.__index = (idx if idx < len(self) else 0)
        self.status()

    def next(self):
        """Reposition index to next item."""
        if self.__index > 0:
            self.__index -= 1
        self.status()

    def previous(self):
        """Reposition index to previous item."""
        if self.__index < len(self) - 1:
            self.__index += 1
        self.status()

    def first(self):
        """'first' actually kind of means 'last', since this is a FIFO stack."""
        self.__index = len(self) - 1
        self.status()

    def last(self):
        """'last' actually kind of means 'first', since this is a FIFO stack."""
        self.__index = 0
        self.status()

    def show_in_status_bar(self):
        """Show current item in status bar."""
        copy = self.current()
        if copy:
            copy = copy.replace("\t", "\\t")
            copy = copy.replace("\n", "\\n")
            copy = copy.replace("\r", "\\r")
            sublime.status_message(u'Set Clipboard to "{copy}"'.format(copy=copy))
        else:
            sublime.status_message('Nothing in history')

    def status(self):
        """Status."""
        copy = self.current()
        if copy:
            set_clip(self.current())
        else:
            sublime.status_message('Nothing in history')

# ============================================================================


class ClipboardManager(sublime_plugin.TextCommand):
    """Main class."""

    action, indent, pop, List = False, False, False, None
    yanking, yank_choice, idx = False, False, None

    def paste(self, msg='Nothing in history'):
        """Paste item."""
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
        """Yank item."""
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

            if YANK_MODE and not len(YANK) and explicit_yank_mode:
                if sets.get('end_yank_mode_on_emptied_stack', False):
                    self.view.window().run_command('clipboard_manager_yank_mode')

        else:
            sublime.status_message('Nothing to yank')

    def clear_yank_list(self):
        """Clear yank list."""
        global YANK
        YANK = HistoryList()
        sublime.status_message('Yank history cleared')

    def clear_history(self):
        """Clear history."""
        global HISTORY
        HISTORY = HistoryList()
        sublime.status_message('Clipboard history cleared')

    def next(self):
        """Next item in history."""
        HISTORY.next()
        update_output_panel(self.view.window())
        clipboard_display(self.view)

    def previous(self):
        """Previous item in history."""
        HISTORY.previous()
        update_output_panel(self.view.window())
        clipboard_display(self.view)

    def paste_next(self):
        """Paste next item."""
        self.paste()
        HISTORY.next()

    def paste_previous(self):
        """Paste previous item."""
        HISTORY.previous()
        self.paste()

    def choice_panel(self, index):
        """Choice panel."""
        args = self.List, index
        clipboard_display(self.view, args)

    def choose_and_paste(self, msg='Nothing in history'):
        """Choose and paste."""
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
            self.view.hide_popup()
            self.view.window().run_command('clipboard_manager_update_panel', {"close": True})

        if lines:
            sublime.active_window().show_quick_panel(lines, on_done, 2, -1, self.choice_panel)
        else:
            sublime.status_message(msg)

    def register(self, x):
        """Register."""
        if self.action == 'copy':
            self.view.run_command("clipboard_manager_copy_to_register", {"register": x})
        elif self.action == 'paste':
            self.view.run_command('clipboard_manager_paste_from_register', {"register": x, "indent": self.indent})

    def run(self, edit, **kwargs):
        """Run."""
        args = {"paste": self.paste, "yank": self.yank, "clear_yank_list": self.clear_yank_list,
                "clear_history": self.clear_history, "next": self.next, "previous": self.previous,
                "paste_next": self.paste_next, "paste_previous": self.paste_previous,
                "choice_panel": self.choice_panel, "choose_and_paste": self.choose_and_paste,
                "register": self.register}

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
            args[arg]()

# ===========================================================================


class ClipboardManagerCommandMode(sublime_plugin.TextCommand):
    """
    Enter command mode if not active, restore previous state when exiting.

        L.command_mode = (bool, bool)
        [0] is True if this command has been activated
        [1] is the previous state of command mode
    """

    def run(self, edit):
        """Run."""
        ClipboardManagerListener.command_mode = True
        self.view.set_status("clip_man", "  Clipboard Manager: awaiting command  ")

# ===========================================================================


class ClipboardManagerYankMode(sublime_plugin.TextCommand):
    """Set yank mode."""

    def run(self, edit):
        """Run."""
        global YANK_MODE

        YANK_MODE = not YANK_MODE
        msg = 'On' if YANK_MODE else 'Off'
        sublime.status_message("  YANK MODE:  " + msg)

# ===========================================================================


class ClipboardManagerUpdatePanel(sublime_plugin.TextCommand):
    """Show current clip in output panel."""

    def run(self, edit, args=False, close=False):
        """Run."""
        if close:
            self.view.window().destroy_output_panel('choose_and_paste')
            return

        scheme, syntax, index, List = args
        w = sublime.active_window()
        v = w.create_output_panel('choose_and_paste')
        w.run_command("show_panel", {"panel": "output.choose_and_paste"})
        v.settings().set('syntax', syntax)
        v.settings().set('color_scheme', scheme)

        all = sublime.Region(0, v.size())
        v.erase(edit, all)
        v.insert(edit, 0, List[index])


class ClipboardManagerRegister(sublime_plugin.TextCommand):
    """Copy to or paste from register."""

    def copy(self, s):
        """Copy to register."""
        self.view.run_command('copy')
        content = get_clip()
        HISTORY.register(s, content)
        update_output_panel(self.view.window(), True)
        sublime.active_window().status_message("   Registered in " + s)

    def paste(self, s):
        """Paste from register."""
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
        """Execute on valid entered character."""
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
        elif self.mode == "copy":
            self.copy(s)
        elif self.mode == "paste":
            self.paste(s)
        w.run_command('hide_panel')

    def run(self, edit, mode='copy', indent=False, reset='letters'):
        """Run."""
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
    """Show history in output panel."""

    def run(self, yank=False):
        """Run."""
        self.window.run_command('show_panel', {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window, yank=yank)


class ClipboardManagerShowRegisters(sublime_plugin.WindowCommand):
    """Show registers in output panel."""

    def run(self):
        """Run."""
        self.window.run_command('show_panel', {'panel': 'output.clipboard_manager'})
        update_output_panel(self.window, True)


class ClipboardManagerEdit(sublime_plugin.TextCommand):
    """History manipulation command."""

    def ibooks():
        """Remove ibook quotes."""
        for i, clip in enumerate(HISTORY):
            quotes_re = re.compile(r'^“(.*?)”\s+Excerpt From:.*$', re.DOTALL)
            match = quotes_re.search(clip)
            if match:
                clip = match.group(1)
                HISTORY[i] = clip

    def run(self, edit, action="ibooks"):
        """Run."""
        if action == "ibooks":
            self.ibooks()

# ============================================================================


class ClipboardManagerListener(sublime_plugin.EventListener):
    """Main listener."""

    just_run = False
    command_mode = False

    def on_text_command(self, view, command_name, args):
        """on_text_command event."""
        if self.just_run:
            self.just_run = False

        elif command_name in ['copy', 'cut']:
            self.just_run = True
            view.run_command(command_name)
            if Vsl:
                Vsl.process_command(Vsl, view)
            append_clipboard()
            update_output_panel(view.window())
            return "ClipboardManagerListener"

    def on_query_context(self, view, key, operator, operand, match_all):
        """on_query_context event."""
        if key == "clip_man":
            if operator == sublime.OP_EQUAL and operand == "yank_mode":
                return explicit_yank_mode

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
    """Dummy command."""

    def run(self, edit, content):
        """Run."""
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
