"""Sublime Clipboard Manager."""
import sublime
import sublime_plugin
import re
from mdpopups import show_popup as mdpopup, add_phantom as mdph, syntax_highlight as synhl

HISTORY, YANK, YANK_MODE = None, None, False

CSS = """
    .mdpopups div.highlight,
    .mdpopups pre.highlight {
        border: 2px solid var(--mdpopups-hl-border);
        padding: 0.5rem;
        margin-bottom: 0;
        font-size: 1rem;
    }
"""

INLINE = """
    body {
        border: 2px solid var(--mdpopups-hl-border);
        padding: 0.5rem;
    }
"""


def plugin_loaded():
    """On restart."""
    global HISTORY, YANK, YANK_MODE
    global Vsl, sets, explicit_yank_mode, allow_history_duplicates

    sets = sublime.load_settings("clipboard_manager.sublime-settings")
    sets.add_on_change('clipboard_manager', on_settings_change)

    try:
        from VirtualSpace.VirtualSpace import VirtualSpaceListener as Vsl
    except ImportError:
        Vsl = False

    HISTORY = HistoryList()
    HISTORY.append(get_clip())
    YANK = HistoryList()

    explicit_yank_mode = sets.get('explicit_yank_mode', False)
    allow_history_duplicates = sets.get('allow_history_duplicates', False)
    # allow copying to yank list already, if explicit mode is off
    YANK_MODE = not explicit_yank_mode

# ============================================================================


def on_settings_change():
    """Update settings."""
    global explicit_yank_mode, allow_history_duplicates
    explicit_yank_mode = sets.get('explicit_yank_mode', False)
    allow_history_duplicates = sets.get('allow_history_duplicates', False)


def get_clip():
    """Get clipboard content."""
    return sublime.get_clipboard()


def set_clip(s):
    """Set clipboard content."""
    while s != get_clip():
        sublime.set_clipboard(s)


def append_clipboard():
    """Append the contents of the clipboard to the HISTORY and YANK globals."""
    clip = get_clip()
    if YANK_MODE:
        YANK.append(clip)
        # if explicit_yank_mode is active, use only yank list
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


def inline_popup(content):
    """Show message in popup at cursor."""
    v = sublime.active_window().active_view()
    show_popup(v, content)
    # close open panels, if any
    sublime.active_window().run_command('hide_panel')


def popup_content(st, syntax):
    """Format content for popup."""
    syntax = syntax if st.count('\n') else ''
    return "```" + syntax + "\n" + (st[:350] + "\n...\n" if len(st) > 500 else st) + "\n```"


def show_popup(v, content, loc=-1, css=INLINE):
    """Show popup."""
    mdpopup(v, content, flags=sublime.HIDE_ON_MOUSE_MOVE_AWAY, css=css, location=loc, max_width=2000)


def hide_all():
    """Hide popups/panels."""
    sublime.active_window().active_view().hide_popup()
    sublime.active_window().run_command('clipboard_manager_update_panel', {"close": True})

# ============================================================================


def clipboard_display(v, args=False):
    """Display selected clipboard content in panel or popup."""
    panel, popup = False, False
    mode = sets.get("display_mode") if not ClipboardManagerListener.command_mode \
        else sets.get("command_mode_display_mode")

    if mode == "panel":
        panel = True
    elif mode == "popup":
        popup = True
    elif mode == "status_bar":
        HISTORY.show_in_status_bar()
        return
    else:
        return

    (List, index) = args if args else (HISTORY, HISTORY.current_index())
    if index is None:   # no more clips
        return
    syntax, scheme, codeblock_syn = List.clip_syntaxes[index]

    # calling a panel
    if panel:
        args = (scheme, syntax, index, List.clips)
        v.window().run_command('clipboard_manager_update_panel', {"args": args})
        return

    # showing popup instead

    if popup and args:
        # popup showed along with quick panel (choose&paste)
        offset = sets.get('popup_vertical_offset')
        max = sets.get('max_quick_panel_items')
        limit = len(List.clips) if len(List.clips) < max else max
        vis = v.visible_region()
        vis_a = v.text_to_layout(vis.a)[1]
        vis_b = v.text_to_layout(vis.b)[1]
        mod_height = (offset - 20 * limit) if offset else 0
        loc = v.layout_to_text((0, int((vis_a + vis_b) / 2 - mod_height)))

        st = List.clips[index]
        content = popup_content(st, codeblock_syn)
        show_popup(v, content, loc, CSS)
    else:
        # inline popup called when using previous/next in command mode
        st = HISTORY.current()
        content = popup_content(st, codeblock_syn)
        show_popup(v, content, css=CSS)

# ============================================================================


class HistoryList(object):
    """Object for storing the history. Maintains a "pointer" to the current clipboard item."""

    def __init__(self):
        """Initialize history."""
        self.clips = []
        self.registers = {}
        self.max_clips = 256
        self.__index = 0
        self.clip_syntaxes = []

    def show(self, yank=False):
        """Show history entries in output panel."""
        title = 'YANK' if yank else 'CLIPBOARD'
        ret = ""
        ret += " " + title + " HISTORY (%d)\n" % len(self.clips)
        ret += "====================%s==\n" % ("=" * len(str(len(self.clips))))
        for i, item in enumerate(self.clips):
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
        ret += "=====================%s==\n" % ("=" * len(str(len(self.registers.items()))))
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

    def register(self, register, st=None):
        """Save to specific register, or retrieve from register."""
        if st:
            self.registers[register] = st
            content = popup_content(st, self.clip_syntax()[2])
            inline_popup('Set Clipboard Register "{0}" to:\n\n{1}'.format(register, content))
        else:
            return self.registers[register]

    def clip_syntax(self):
        """Store syntax/scheme for popup or panel display."""
        view = sublime.active_window().active_view()
        supported = sets.get("popup_syntaxes")
        codeblock_syn = ''
        for syn in supported:
            for s in supported[syn]:
                if view.score_selector(0, s):
                    codeblock_syn = syn
                    break
        return (view.settings().get('syntax'), view.settings().get('color_scheme'), codeblock_syn)

    def append(self, item):
        """Append to the history, or reposition item if already present."""
        skip = False

        def insert_item(item):
            self.__index = 0
            if not skip:
                self.clips.insert(0, item)
                self.clip_syntaxes.insert(0, self.clip_syntax())

            if len(self.clips) > self.max_clips:
                del self.clips[-1]
                del self.clip_syntaxes[-1]

        if YANK_MODE:
            v = sublime.active_window().active_view()
            if self.clips and item == self.clips[0] and len(v.sel()) == 1:
                skip = True
            elif sets.get('yank_disjoin_multiple_cursors', False):
                for sel in v.sel():
                    substr = v.substr(sel)
                    if substr:
                        insert_item(substr)
                return

        # if allowing duplicates, only check the last clip

        elif self.clips:
            if item == self.clips[0]:
                skip = True
            elif not allow_history_duplicates and item in self.clips:
                ix = self.clips.index(item)
                del self.clips[ix]
                del self.clip_syntaxes[ix]

        insert_item(item)

    def current(self):
        """Return item at current history index."""
        return self.clips[self.__index] if len(self.clips) else None

    def current_index(self):
        """Return current history index."""
        return self.__index if len(self.clips) else None

    def at(self, idx):
        """Reposition index."""
        self.__index = (idx if idx < len(self.clips) else 0 if self.clips else None)
        self.status()

    def next(self):
        """Reposition index to next item."""
        if self.__index > 0:
            self.__index -= 1
        self.status()

    def previous(self):
        """Reposition index to previous item."""
        if self.__index < len(self.clips) - 1:
            self.__index += 1
        self.status()

    def first(self):
        """'first' actually kind of means 'last', since this is a FIFO stack."""
        self.__index = len(self.clips) - 1
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
            inline_popup('Nothing in history')

    def status(self):
        """Status."""
        copy = self.current()
        if copy:
            set_clip(self.current())
        else:
            inline_popup('Nothing in history')

# ============================================================================


class ClipboardManager(sublime_plugin.TextCommand):
    """Main class."""

    action, indent, pop, List = False, False, False, None
    yanking, yank_choice, idx = False, False, None

    # ---------------------------------------------------------------------------

    def paste(self, yanking=False):
        """Paste item."""
        List = self.List
        msg = 'Nothing in history' if not yanking else 'Nothing in yank stack'

        if not len(List.clips):
            inline_popup(msg)
            return

        # ensure correct clipboard content
        clip = List.current()
        set_clip(clip)

        if self.indent:
            self.view.run_command('paste_and_indent')
        else:
            self.view.run_command('paste')

        if self.pop:
            ix = List.clips.index(clip)
            del List.clips[ix]
            del List.clip_syntaxes[ix]
            if not List.clips:
                inline_popup(msg)

        update_output_panel(self.view.window(), yank=yanking)

    # ---------------------------------------------------------------------------

    def yank(self, choice):
        """Yank item."""
        if len(YANK.clips):
            self.List = YANK

            if choice:
                self.choose_and_paste(yanking=True)

            # self.idx starts as None. If it's not, it's because yanking didn't
            # start from the bottom, but from somewhere via choose&paste
            # in this case, yanking must proceed from that point

            elif self.idx is not None and (len(YANK.clips) - 1) >= self.idx:
                # keep yanking from where you left the quick panel,
                # reducing index because the previous one has been eaten
                YANK.at(self.idx - 1)
                self.idx -= 1
                # if index goes below zero, it reached the top and must start
                # again from the bottom, if there's something left
                if self.idx < 0:
                    self.idx = None
                self.paste(yanking=True)

            else:
                # keep popping the bottom-most index
                YANK.first()
                self.paste(yanking=True)

            if YANK_MODE and not len(YANK.clips) and explicit_yank_mode:
                if sets.get('end_yank_mode_on_emptied_stack', False):
                    self.view.window().run_command('clipboard_manager_yank_mode')

        else:
            inline_popup('Nothing to yank')

    # ---------------------------------------------------------------------------

    def choose_and_paste(self, yanking=False):
        """Choose and paste."""
        def format(line):
            return line.replace('\n', '\\n')[:64]

        List = self.List
        if not len(List.clips):
            inline_popup('Nothing in history')
            return
        lines = [format(clip) for clip in List.clips]

        def on_done(idx):
            if idx >= 0:
                self.idx = idx
                List.at(idx)
                self.paste(yanking)
            else:
                List.at(0)
            hide_all()

        sublime.active_window().show_quick_panel(lines, on_done, 2, -1, self.choice_panel)

    # ---------------------------------------------------------------------------

    def clear_yank_list(self):
        """Clear yank list."""
        global YANK
        YANK = HistoryList()
        sublime.status_message('Yank history cleared')
        inline_popup('Yank history cleared')

    def clear_history(self):
        """Clear history."""
        global HISTORY
        HISTORY = HistoryList()
        sublime.status_message('Clipboard history cleared')
        inline_popup('Clipboard history cleared')

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
        """Paste and select next item."""
        self.paste()
        self.next()

    def paste_previous(self):
        """Paste and select previous item."""
        self.paste()
        self.previous()

    def choice_panel(self, index):
        """Choice panel."""
        self.List.at(index)
        args = self.List, index
        clipboard_display(self.view, args)

    # ---------------------------------------------------------------------------

    def run(self, edit, **kwargs):
        """Run."""
        args = {"paste": self.paste, "yank": self.yank, "clear_yank_list": self.clear_yank_list,
                "clear_history": self.clear_history, "next": self.next, "previous": self.previous,
                "paste_next": self.paste_next, "paste_previous": self.paste_previous,
                "choice_panel": self.choice_panel, "choose_and_paste": self.choose_and_paste}

        if 'indent' in kwargs:
            self.indent = True
            del kwargs['indent']
        else:
            self.indent = False

        if 'pop' in kwargs:
            self.pop = True
            del kwargs['pop']
        else:
            self.pop = False

        if 'yank' in kwargs:
            self.pop = True
            self.yank('choose' in kwargs)
            return
        else:
            self.List = HISTORY

        for arg in kwargs:
            args[arg]()

# ===========================================================================


class ClipboardManagerCommandMode(sublime_plugin.TextCommand):
    """Toggle command mode."""

    def run(self, edit):
        """Run."""
        ClipboardManagerListener.command_mode = True
        self.view.set_status("clip_man", "  Clipboard Manager: awaiting command  ")

# ===========================================================================


class ClipboardManagerYankMode(sublime_plugin.TextCommand):
    """Set yank mode."""

    def run(self, edit):
        """Run."""
        global YANK_MODE, YANK

        YANK_MODE = not YANK_MODE
        sublime.status_message("  YANK MODE:  " + ('On' if YANK_MODE else 'Off'))

        # clear yank list if manually exiting yank mode
        if not YANK_MODE and explicit_yank_mode:
            YANK = HistoryList()

# ===========================================================================


class ClipboardManagerUpdatePanel(sublime_plugin.TextCommand):
    """Show current clip in output panel."""

    def run(self, edit, args=False, close=False):
        """Run."""
        w = sublime.active_window()

        if close:
            w.destroy_output_panel('choose_and_paste')
            return

        scheme, syntax, index, clips = args
        # syntax is plain text if there are no new lines
        syntax = syntax if clips[index].count('\n') else 'Packages/Text/Plain text.tmLanguage'

        v = w.create_output_panel('choose_and_paste')
        w.run_command("show_panel", {"panel": "output.choose_and_paste"})
        v.settings().set('syntax', syntax)
        v.settings().set('color_scheme', scheme)

        all = sublime.Region(0, v.size())
        v.erase(edit, all)
        v.insert(edit, 0, clips[index])

# ===========================================================================


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
            sublime.active_window().status_message("   Pasted register " + s)
            set_clip(HISTORY.register(s))
            if self.indent:
                self.view.run_command('paste_and_indent')
            else:
                self.view.run_command('paste')
        else:
            sublime.active_window().status_message("   Not a valid register")

    def set_clip(self, s):
        """Set to clipboard."""
        if s in HISTORY.registers:
            sublime.active_window().status_message("   Clipboard set to register '" + s + "'")
            set_clip(HISTORY.register(s))
        else:
            sublime.active_window().status_message("   Not a valid register")
        self.view.close()

    def on_change(self, s):
        """Execute on valid entered character."""
        if not s:
            return

        s = s[0]
        chars = "abcdefghijklmnopqrstuvwxyz" + \
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"

        w = sublime.active_window()
        if s not in chars:
            w.status_message("   Not a valid key.")
            w.run_command('hide_panel')
            return
        elif self.mode == "copy":
            self.copy(s)
        elif self.mode == "paste":
            self.paste(s)
        elif self.mode == "set":
            self.set_clip(s)
        w.run_command('hide_panel')

    def run(self, edit, mode='copy', indent=False, reset='letters'):
        """Run."""
        msg = ('  Register in registers key?', '  Paste from registers key?', '  Set clipboard to registers key?')

        if mode == "reset":
            HISTORY.reset_register(reset)
            return

        msg = msg[0] if mode == 'copy' else msg[1] if mode == 'paste' else msg[2]
        sublime.active_window().status_message(msg)
        self.indent, self.mode = indent, mode

        s = "Enter a key (0-9, a-Z):"
        sublime.active_window().show_input_panel(s, "", None, self.on_change, None)

# ============================================================================


class ClipboardManagerShow(sublime_plugin.WindowCommand):
    """Show history or registers in output panel or buffer."""

    def run(self, yank=False, register=False):
        """Run."""
        if sets.get('show_records', "panel") == "panel":
            self.window.run_command('show_panel', {'panel': 'output.clipboard_manager'})
            if register:
                update_output_panel(self.window, True)
            else:
                update_output_panel(self.window, yank=yank)
        else:
            self.window.run_command('clipboard_manager_buffer', {'yank': yank, 'register': register})


class ClipboardManagerBuffer(sublime_plugin.TextCommand):
    """Render clipboard history in a buffer."""

    def create_view(self, edit, register, yank):
        """Create buffer and set attributes."""
        Cml = ClipboardManagerListener
        Cml.Buffer_list = HISTORY if not yank else YANK
        _list = '\nREGISTERS' if register else '\nCLIPBOARD HISTORY' if not yank else '\nYANK HISTORY'

        v = self.v = sublime.active_window().new_file()
        v.set_name(_list[1:])
        v.set_scratch(True)
        v.set_syntax_file('Packages/Clipboard Manager/clipman_buffer.sublime-syntax')
        v.settings().set('color_scheme', sets.get('show_records_scheme'))
        v.settings().set('font_size', 8)
        v.settings().set("line_padding_bottom", 0)
        v.settings().set("line_padding_top", 0)

        # header
        post = '\n   [q] Close view   [c] Set clipboard   [t] Text mode'
        header = _list + '\n\n' + post + '\n' + '-' * 55 + '\n\n'
        v.insert(edit, 0, header)

    def copy_input(self, n):
        """Input for clipboard entry."""
        Cml = ClipboardManagerListener

        try:
            if int(n) < len(Cml.Buffer_list.clips):
                Cml.Buffer_list.at(int(n))
                Cml.Buffer_list.status()
                sublime.status_message("    Set clipboard to entry n." + n)
            else:
                sublime.status_message("    Entry n." + n + " doesn't exist.")
            self.view.close()
        except (TypeError, ValueError):
            sublime.status_message("    You entered a wrong value.")
            self.view.close()

    def run(self, edit, register=False, yank=False, action=False):
        """Run."""
        Cml, text = ClipboardManagerListener, False

        if action == "text":
            self.view.close()
            text = True
        elif action == "quit":
            self.view.close()
            return
        elif action == "copy" and Cml.Buffer_register:
            sublime.active_window().run_command('clipboard_manager_register', {'mode': 'set'})
            return
        elif action == "copy":
            sublime.active_window().show_input_panel('Enter an entry:', '', self.copy_input, None, None)
            return

        self.create_view(edit, register, yank)
        Cml.Buffer_register = register

        def sz():
            return self.v.size()

        def _clip(c):
            st = c[:350] + "\n...\n" if len(c) > 500 else c
            hl = Cml.Buffer_list.clip_syntaxes[n][2] if Cml.Buffer_list.clip_syntaxes[n][2] else 'text'
            return synhl(self.v, st, hl)

        def _text(c):
            return c[:350] + "\n...\n" if len(c) > 500 else c

        # content for register
        if register:
            for r in HISTORY.registers:
                self.v.insert(edit, sz(), r + '.\n')
                if text:
                    self.v.insert(edit, sz(), _text(HISTORY.registers[r]))
                    self.v.insert(edit, sz(), "-" * 55 + '\n')
                else:
                    mdph(self.v, "clpman", sublime.Region(sz(), sz()),
                         _clip(HISTORY.registers[r]), sublime.LAYOUT_INLINE)
                    self.v.insert(edit, sz(), '\n\n')
            return

        # content for histories
        for n, c in enumerate(Cml.Buffer_list.clips):
            self.v.insert(edit, sz(), str(n) + '.\n')
            if text:
                self.v.insert(edit, sz(), _text(c))
                self.v.insert(edit, sz(), "-" * 55 + '\n')
            else:
                mdph(self.v, "clpman", sublime.Region(sz(), sz()), _clip(c), sublime.LAYOUT_INLINE)
                self.v.insert(edit, sz(), '\n\n')

        self.v.set_read_only(True)


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
                    hide_all()
                return True
            else:
                ClipboardManagerListener.command_mode = False
                view.erase_status("clip_man")
                hide_all()
        return None


class ClipboardManagerDummy(sublime_plugin.TextCommand):
    """Dummy command."""

    def run(self, edit, content):
        """Run."""
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
