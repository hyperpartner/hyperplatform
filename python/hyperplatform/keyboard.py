from __future__ import annotations

from typing import List, Dict, Optional, Literal


class InlineKeyboardButton:
    def __init__(self, text: str, callback_data: str, align: Literal['left', 'right', 'center'] = 'center'):
        self.text = text
        self.callback_data = callback_data
        self.align = align

    def to_dict(self) -> Dict[str, str]:
        return {"text": self.text, "callback_data": self.callback_data, "align": self.align}


class InlineKeyboardMarkup:
    def __init__(self, rows: Optional[List[List[InlineKeyboardButton]]] = None):
        # rows можно не передавать, тогда будет пустая клавиатура
        self.rows: List[List[InlineKeyboardButton]] = rows or []

    def row(self, *buttons: InlineKeyboardButton) -> "InlineKeyboardMarkup":
        self.rows.append(list(buttons))
        return self

    def to_list(self) -> List[List[Dict[str, str]]]:
        return [[b.to_dict() for b in row] for row in self.rows]


class TextButton:
    def __init__(self,
                 text: str,
                 cb_data: str = '',
                 bg_color: str = "#228B22",
                 text_color: str = "#ffffff",
                 blinking: float = 0.0
                 ) -> None:
        self.text = text
        self.cb_data = cb_data
        self.bg_color = bg_color
        self.text_color = text_color
        self.blinking = blinking


    @property
    def html(self) -> str:
        blink = f' data-blinking="{self.blinking}"' if self.blinking else ''
        inact = '' if self.cb_data else ' inactive '
        return f'<callback {inact} data-cb="{self.cb_data}"{blink} style="--cb-bg:{self.bg_color};--cb-text:{self.text_color};">{self.text}</callback>'
