"""Sublime Clipboard Manager."""
import sublime
import sublime_plugin
import os
import re
import json
from mdpopups import show_popup as mdpopup, add_phantom as mdph, syntax_highlight as synhl

HISTORY, YANK, YANK_MODE = None, None, False
numbers = "1234567890"
lettersl = "abcdefghijklmnopqrstuvwxyz"
lettersu = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

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
    global Vsl, sets, explicit_yank_mode, allow_history_duplicates, reg_json

    sets = sublime.load_settings("clipboard_manager.sublime-settings")
    sets.add_on_change('clipboard_manager', on_settings_change)
    reg_json = os.path.join(sublime.packages_path(), "User", "clipman_registers.json")
    try:
        from VirtualSpace.VirtualSpace import VirtualSpaceListener as Vsl
    except ImportError:
        Vsl = False

    HISTORY = HistoryList()
    HISTORY.append(get_clip())
    YANK = HistoryList()

    if sets.get('import_registers', False):
        if not os.path.isfile(reg_json):
            with open(reg_json, 'w') as f:
                json.dump({}, f)
        else:
            HISTORY.registers = json.load(open(reg_json))

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

    def __reset__(self):
        """Reset history, keeping registers."""
        self.clips = []
        self.clip_syntaxes = []
        self.__index = 0

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
        if what == "numbers":
            for n in numbers:
                self.registers[n] = ""
        elif what == "lettersl":
            for n in lettersl:
                self.registers[n] = ""
        elif what == "lettersu":
            for n in lettersu:
                self.registers[n] = ""
        else:
            self.registers = {}

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

        self.view.show_at_center(self.view.sel()[-1].b)
        hide_all()

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
        HISTORY.__reset__()
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

    def previous_and_paste(self):
        """Select next item and paste."""
        self.previous()
        self.paste()

    def next_and_paste(self):
        """Select previous item and paste."""
        self.next()
        self.paste()

    def paste_and_next(self):
        """Paste and select next item."""
        self.paste()
        self.next()

    def paste_and_previous(self):
        """Paste and select previous item."""
        self.paste()
        self.previous()

    def paste_and_display(self):
        """Paste and keep displaying popup/panel."""
        self.paste()
        clipboard_display(self.view)

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
                "paste_and_next": self.paste_and_next, "paste_and_previous": self.paste_and_previous,
                "next_and_paste": self.next_and_paste, "previous_and_paste": self.previous_and_paste,
                "choice_panel": self.choice_panel, "choose_and_paste": self.choose_and_paste,
                "paste_and_display": self.paste_and_display}

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
    """Toggle yank mode."""

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

    def options(self):
        """Backup options."""
        items = [['Export', 'Save current registers to file'],
                 ['Import', 'Restore register keys from file'],
                 ['Erase', 'Erase selected register keys from file'],
                 ['Reset', 'Reset selected register keys from current memory'],
                 ['Edit', 'Open file for manual edits'],
                 ['Delete', 'Delete file permanently']]

        def on_done(ix):
            if ix == 0:
                self.export_to()
            elif ix == 1:
                self.import_from()
            elif ix == 2:
                self.erase()
            elif ix == 3:
                self.reset()
            elif ix == 4:
                sublime.active_window().open_file(reg_json)
            elif ix == 5:
                os.remove(reg_json)

        sublime.active_window().show_quick_panel(items, on_done)

    def export_to(self):
        """Export selected registers to json file."""
        items = [['All', 'Export all registers'],
                 ['Numbers', 'Export only numeric registers'],
                 ['Letters (a-z)', 'Export only lowercase literal registers'],
                 ['Letters (A-Z)', 'Export only uppercase literal registers']]

        if not sets.get('import_registers', False):
            sublime.status_message("   Attention: Import from file is currently disabled.")

        data = HISTORY.registers
        nums = {n: data[n] for n in data if n in numbers and data[n]}
        letsL = {l: data[l] for l in data if l in lettersl and data[l]}
        letsU = {l: data[l] for l in data if l in lettersu and data[l]}
        _all = nums.copy()
        _all.update(letsL)
        _all.update(letsU)

        def on_done(ix):
            if ix == 0:
                json.dump(_all, open(reg_json, 'w'), indent=2)
            elif ix == 1:
                json.dump(nums, open(reg_json, 'w'), indent=2)
            elif ix == 2:
                json.dump(letsL, open(reg_json, 'w'), indent=2)
            elif ix == 3:
                json.dump(letsU, open(reg_json, 'w'), indent=2)

        sublime.active_window().show_quick_panel(items, on_done)

    def import_from(self):
        """Import selected registers from json file."""
        items = [['All', 'Import all registers'],
                 ['Numbers', 'Import only numeric registers'],
                 ['Letters (a-z)', 'Import only lowercase literal registers'],
                 ['Letters (A-Z)', 'Import only uppercase literal registers']]

        if not sets.get('import_registers', False):
            sublime.status_message("   Attention: Import from file is currently disabled.")

        data = json.load(open(reg_json))
        nums = {n: data[n] for n in data if n in numbers and data[n]}
        letsL = {l: data[l] for l in data if l in lettersl and data[l]}
        letsU = {l: data[l] for l in data if l in lettersu and data[l]}

        def on_done(ix):
            if ix == 0:
                HISTORY.registers.update(nums)
                HISTORY.registers.update(letsL)
                HISTORY.registers.update(letsU)
            elif ix == 1:
                HISTORY.registers.update(nums)
            elif ix == 2:
                HISTORY.registers.update(letsL)
            elif ix == 3:
                HISTORY.registers.update(letsU)

        sublime.active_window().show_quick_panel(items, on_done)

    def erase(self):
        """Erase selected register keys from file."""
        items = [['All', 'Erase all registers'],
                 ['Numbers', 'Erase only numeric registers'],
                 ['Letters (a-z)', 'Erase only lowercase literal registers'],
                 ['Letters (A-Z)', 'Erase only uppercase literal registers']]

        if not sets.get('import_registers', False):
            sublime.status_message("   Attention: Import from file is currently disabled.")

        def on_done(ix):
            if ix >= 0:
                data = json.load(open(reg_json))
                if ix == 0:
                    data = {}
                elif ix == 1:
                    data = {n: data[n] for n in data if n not in numbers}
                elif ix == 2:
                    data = {l: data[l] for l in data if l not in lettersl}
                elif ix == 3:
                    data = {l: data[l] for l in data if l not in lettersu}
                with open(reg_json, 'w') as f:
                    json.dump(data, f, indent=2)

        sublime.active_window().show_quick_panel(items, on_done)

    def reset(self):
        """Reset selected register keys from memory."""
        items = [['All', 'Reset all registers'],
                 ['Numbers', 'Reset only numeric registers'],
                 ['Letters (a-z)', 'Reset only lowercase literal registers'],
                 ['Letters (A-Z)', 'Reset only uppercase literal registers']]

        def on_done(ix):
            if ix == 0:
                HISTORY.reset_register("all")
            elif ix == 1:
                HISTORY.reset_register("numbers")
            elif ix == 2:
                HISTORY.reset_register("lettersl")
            elif ix == 3:
                HISTORY.reset_register("lettersu")

        sublime.active_window().show_quick_panel(items, on_done)

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
        chars = numbers + lettersl + lettersu

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

        if mode == "options":
            self.options()
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

        if not text:
            Cml.Buffer_register = register
        self.create_view(edit, Cml.Buffer_register, yank)

        def sz():
            return self.v.size()

        def _clip(c):
            st = c[:350] + "\n...\n" if len(c) > 500 else c
            hl = Cml.Buffer_list.clip_syntaxes[n][2] if Cml.Buffer_list.clip_syntaxes[n][2] else 'text'
            return synhl(self.v, st, hl)

        def _text(c):
            c = c[:350] + "\n...\n" if len(c) > 500 else c
            c = "\t" + c.replace("\n", "\n\t")
            return c

        # content for register
        if Cml.Buffer_register:
            regs = sorted(r for r in HISTORY.registers)
            for r in regs:
                self.v.insert(edit, sz(), r + '.\n')
                if text:
                    self.v.insert(edit, sz(), _text(HISTORY.registers[r]))
                    self.v.insert(edit, sz(), '\n' + "-" * 55 + '\n')
                else:
                    loc = sublime.Region(sz(), sz())
                    mdph(self.v, "clpman", loc, _text(HISTORY.registers[r]), sublime.LAYOUT_INLINE)
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

    def deactivate_command_mode(self, view):
        """Deactivate command mode."""
        ClipboardManagerListener.command_mode = False
        view.erase_status("clip_man")
        hide_all()

    def on_text_command(self, view, command_name, args):
        """on_text_command event."""
        if "clipboard_manager" not in command_name:
            if ClipboardManagerListener.command_mode:
                self.deactivate_command_mode(view)
            elif sublime.active_window().get_output_panel('choose_and_paste'):
                hide_all()

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
                    self.deactivate_command_mode(view)
                return True
            else:
                self.deactivate_command_mode(view)
        return None


class ClipboardManagerDummy(sublime_plugin.TextCommand):
    """Dummy command."""

    def run(self, edit, content):
        """Run."""
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, '')
        self.view.insert(edit, 0, content)
