import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any, cast

from .fp_core import (
    build_flashcards_csv_rows,
    parse_flashcards_from_text,
    render_flashcards_text,
    render_glossary_text,
    render_key_points_text,
    render_outline_text,
    render_questions_text,
    safe_name,
)


class UIResultsMixin:
    sections: dict[str, tk.Text]

    def _t(self, key: str, **kwargs: Any) -> str:
        try:
            return key.format(**kwargs)
        except Exception:
            return key

    def _open_results(self, outs: dict[str, Any]):
        def set_tab(name: str, value: Any):
            widget = self.sections.get(name)
            if widget is not None:
                widget.delete("1.0", tk.END)
                widget.insert("1.0", str(value or ""))

        set_tab("abstract", outs.get("abstract", ""))
        set_tab("summary_markdown", outs.get("summary_markdown", ""))
        set_tab("outline", render_outline_text(outs.get("outline", [])))
        set_tab("key_points", render_key_points_text(
            outs.get("key_points", [])))
        set_tab(
            "questions",
            render_questions_text(
                outs.get("questions", []),
                answer_label=self._t("answer_label"),
                difficulty_label=self._t("difficulty_label"),
            ),
        )
        set_tab("flashcards", render_flashcards_text(
            outs.get("flashcards", [])))
        set_tab("glossary", render_glossary_text(outs.get("glossary", [])))

    def _export_flashcards_csv(self):
        flashcard_widget = self.sections.get("flashcards")
        if flashcard_widget is None:
            messagebox.showinfo(self._t("dialog_title_no_cards"), self._t(
                "dialog_msg_flashcard_tab_missing"))
            return
        text = flashcard_widget.get("1.0", tk.END)
        cards = parse_flashcards_from_text(text)
        if not cards:
            messagebox.showinfo(self._t("dialog_title_no_cards"), self._t(
                "dialog_msg_no_cards_export"))
            return
        path = filedialog.asksaveasfilename(title=self._t("file_dialog_export_csv"),
                                            defaultextension=".csv",
                                            filetypes=[(self._t("file_dialog_csv"), ".csv")],)
        if not path:
            return
        try:
            import csv
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerows(build_flashcards_csv_rows(cards))
            messagebox.showinfo(self._t("dialog_title_exported"), self._t(
                "dialog_msg_saved_flashcards", path=path))
        except Exception as e:
            messagebox.showerror(self._t("dialog_title_error"), self._t(
                "dialog_msg_export_csv_error", error=e))

    def _safe_name(self, s: str) -> str:
        return safe_name(s)

    def _copy_to_clip(self, s: str):
        try:
            tk.Misc.clipboard_clear(cast(tk.Misc, self))
            tk.Misc.clipboard_append(cast(tk.Misc, self), s)
            tk.Misc.update(cast(tk.Misc, self))
        except Exception:
            pass

    def _save_string(self, s: str, default_name: str):
        path = filedialog.asksaveasfilename(title=self._t("file_dialog_save"), defaultextension=".txt",
                                            initialfile=default_name,
                                            filetypes=[(self._t("file_dialog_text"), ".txt"), (self._t("file_dialog_all"), "*.*")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(s)
            messagebox.showinfo(self._t("dialog_title_saved"), self._t(
                "dialog_msg_saved_file", path=path))
