"""Football match analysis UI prototype."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
import tkinter as tk
import tkinter.font as tkfont

import cv2
from PIL import Image, ImageTk


APP_DIR = Path(__file__).resolve().parent
DEFAULT_OFFSET_SECONDS = -3.0
DEFAULT_DURATION_SECONDS = 600.0
PLAYBACK_TICK_MS = 33
VIDEO_BG = "#0c1419"
PANEL_BG = "#101920"
CARD_BG = "#14212a"
CARD_BG_2 = "#172733"
TEXT_MAIN = "#edf3f7"
TEXT_MUTED = "#93a8b8"
ACCENT = "#1dbf73"
ACCENT_2 = "#4bb3fd"
SUCCESS = "#1dbf73"
FAIL = "#ff5b6e"
FOUL = "#ffbb33"
INFO = "#4bb3fd"


DEFAULT_PLAYERS = [
	"1. Courtois",
	"2. Carvajal",
	"3. Militao",
	"4. Alaba",
	"6. Nacho",
	"8. Kroos",
	"10. Modric",
	"12. Camavinga",
	"15. Valverde",
	"7. Vinicius",
	"11. Rodrygo",
]

DEFAULT_ACTIONS = [
	"패스",
	"드리블",
	"슛",
	"크로스",
	"태클",
	"인터셉트",
	"롱볼",
	"세이브",
	"파울",
]

DEFAULT_RESULTS = [
	"성공",
	"실패",
	"파울 유도",
	"차단",
]

RESULT_COLORS = {
	"성공": SUCCESS,
	"실패": FAIL,
	"파울 유도": FOUL,
	"차단": INFO,
}


def clamp(value: float, minimum: float, maximum: float) -> float:
	return max(minimum, min(maximum, value))


def format_time(seconds: float) -> str:
	seconds = max(0.0, seconds)
	total = int(seconds)
	minutes = total // 60
	sec = total % 60
	return f"{minutes:02d}:{sec:02d}"


def escape_pdf_text(text: str) -> str:
	return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_simple_pdf(lines: list[str], output_path: Path) -> None:
	page_width = 595
	page_height = 842
	margin_left = 48
	margin_top = 54
	max_lines_per_page = 46

	pages = [lines[i : i + max_lines_per_page] for i in range(0, len(lines), max_lines_per_page)] or [["No data"]]
	objects: list[str | bytes] = []

	catalog_object_id = 1
	pages_object_id = 2
	font_object_id = 3

	objects.extend([
		f"<< /Type /Catalog /Pages {pages_object_id} 0 R >>",
		None,
		"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
	])

	page_object_ids: list[int] = []
	content_object_ids: list[int] = []

	next_object_id = 4
	for _page in pages:
		content_object_ids.append(next_object_id)
		next_object_id += 1
		page_object_ids.append(next_object_id)
		next_object_id += 1

	kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
	objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_object_ids)} >>"

	for page_index, page_lines in enumerate(pages):
		content_object_id = content_object_ids[page_index]
		page_object_id = page_object_ids[page_index]
		content_lines = [
			"BT",
			"/F1 12 Tf",
			"14 TL",
			f"{margin_left} {page_height - margin_top} Td",
			f"({escape_pdf_text('Football Analysis Report')}) Tj",
			"T*",
			"/F1 9 Tf",
		]
		for line in page_lines:
			content_lines.append(f"({escape_pdf_text(line)}) Tj")
			content_lines.append("T*")
		content_lines.append("ET")
		content_stream = "\n".join(content_lines).encode("utf-8")
		objects.append(
			f"<< /Length {len(content_stream)} >>\nstream\n".encode("utf-8")
			+ content_stream
			+ b"\nendstream"
		)
		objects.append(
			f"<< /Type /Page /Parent {pages_object_id} 0 R /MediaBox [0 0 {page_width} {page_height}] /Resources << /Font << /F1 {font_object_id} 0 R >> >> /Contents {content_object_id} 0 R >>"
		)

	output = bytearray()
	output.extend(b"%PDF-1.4\n")

	offsets = [0]
	for index, obj in enumerate(objects, start=1):
		offsets.append(len(output))
		output.extend(f"{index} 0 obj\n".encode("utf-8"))
		if isinstance(obj, bytes):
			output.extend(obj)
		else:
			output.extend(obj.encode("utf-8"))
		output.extend(b"\nendobj\n")

	xref_start = len(output)
	output.extend(f"xref\n0 {len(objects) + 1}\n".encode("utf-8"))
	output.extend(b"0000000000 65535 f \n")
	for offset in offsets[1:]:
		output.extend(f"{offset:010d} 00000 n \n".encode("utf-8"))
	output.extend(
		(
			f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_object_id} 0 R >>\n"
			f"startxref\n{xref_start}\n%%EOF\n"
		).encode("utf-8")
	)
	output_path.write_bytes(output)


@dataclass
class EventRecord:
	time_seconds: float
	player: str
	action: str
	result: str


class ShortcutEditor(tk.Toplevel):
	def __init__(self, master: "FootballAnalysisApp") -> None:
		super().__init__(master)
		self.master_app = master
		self.title("단축키 설정")
		self.configure(bg=PANEL_BG)
		self.resizable(False, False)
		self.transient(master)
		self.grab_set()

		self.category_var = tk.StringVar(value="player")
		self.target_var = tk.StringVar()
		self.key_var = tk.StringVar()

		container = tk.Frame(self, bg=PANEL_BG, padx=16, pady=16)
		container.pack(fill="both", expand=True)

		tk.Label(container, text="카테고리", bg=PANEL_BG, fg=TEXT_MAIN).grid(row=0, column=0, sticky="w")
		category_box = ttk.Combobox(container, textvariable=self.category_var, values=["player", "action", "result"], state="readonly", width=18)
		category_box.grid(row=1, column=0, sticky="ew", pady=(4, 12))
		category_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_targets())

		tk.Label(container, text="대상", bg=PANEL_BG, fg=TEXT_MAIN).grid(row=2, column=0, sticky="w")
		self.target_box = ttk.Combobox(container, textvariable=self.target_var, state="readonly", width=32)
		self.target_box.grid(row=3, column=0, sticky="ew", pady=(4, 12))

		tk.Label(container, text="매핑할 키", bg=PANEL_BG, fg=TEXT_MAIN).grid(row=4, column=0, sticky="w")
		key_entry = ttk.Entry(container, textvariable=self.key_var)
		key_entry.grid(row=5, column=0, sticky="ew", pady=(4, 12))

		button_row = tk.Frame(container, bg=PANEL_BG)
		button_row.grid(row=6, column=0, sticky="ew")
		tk.Button(button_row, text="등록", command=self.apply_mapping, bg=ACCENT, fg="#081017", relief="flat", padx=14, pady=8).pack(side="left")
		tk.Button(button_row, text="닫기", command=self.destroy, bg=CARD_BG, fg=TEXT_MAIN, relief="flat", padx=14, pady=8).pack(side="left", padx=8)

		self.preview = tk.Text(container, width=38, height=12, bg=CARD_BG, fg=TEXT_MAIN, insertbackground=TEXT_MAIN, relief="flat")
		self.preview.grid(row=7, column=0, sticky="nsew", pady=(14, 0))
		self.preview.configure(state="disabled")

		container.grid_columnconfigure(0, weight=1)
		self.refresh_targets()
		self.refresh_preview()

	def refresh_targets(self) -> None:
		category = self.category_var.get()
		if category == "player":
			values = self.master_app.players
		elif category == "action":
			values = self.master_app.actions
		else:
			values = self.master_app.results
		self.target_box["values"] = values
		if values and self.target_var.get() not in values:
			self.target_var.set(values[0])

	def refresh_preview(self) -> None:
		lines = ["현재 단축키"]
		for category in ("player", "action", "result"):
			lines.append(f"[{category}]")
			mapping = self.master_app.shortcut_map.get(category, {})
			for key, target in sorted(mapping.items()):
				lines.append(f"  {key.upper()} -> {target}")
		self.preview.configure(state="normal")
		self.preview.delete("1.0", "end")
		self.preview.insert("end", "\n".join(lines))
		self.preview.configure(state="disabled")

	def apply_mapping(self) -> None:
		category = self.category_var.get().strip()
		target = self.target_var.get().strip()
		key = self.key_var.get().strip().lower()
		if not category or not target or not key:
			messagebox.showwarning("단축키 설정", "카테고리, 대상, 키를 모두 입력하세요.", parent=self)
			return
		if len(key) != 1:
			messagebox.showwarning("단축키 설정", "단축키는 한 글자만 입력하세요.", parent=self)
			return
		self.master_app.shortcut_map.setdefault(category, {})[key] = target
		self.master_app.refresh_status(f"단축키 등록: {category} / {target} / {key.upper()}")
		self.refresh_preview()


class FootballAnalysisApp(tk.Tk):
	def __init__(self) -> None:
		super().__init__()
		self.title("축구 경기 분석 프로그램")
		self.configure(bg=VIDEO_BG)
		self.geometry("1560x920")
		self.minsize(1360, 820)

		self.mode_var = tk.StringVar(value="동영상 불러오기")
		self.file_var = tk.StringVar(value="분석할 동영상을 불러오세요")
		self.status_var = tk.StringVar(value="준비 완료")
		self.time_var = tk.DoubleVar(value=0.0)
		self.offset_var = tk.DoubleVar(value=DEFAULT_OFFSET_SECONDS)
		self.speed_var = tk.DoubleVar(value=1.0)
		self.search_var = tk.StringVar(value="")
		self.filter_var = tk.StringVar(value="전체")
		self.summary_var = tk.StringVar(value="이벤트 0개 · 성공률 -")

		self.players = list(DEFAULT_PLAYERS)
		self.actions = list(DEFAULT_ACTIONS)
		self.results = list(DEFAULT_RESULTS)
		self.shortcut_map = {
			"player": {str(index + 1) if index < 9 else "0": name for index, name in enumerate(self.players[:10])},
			"action": {key: name for key, name in zip(["q", "w", "e", "r", "t", "y", "u", "i", "o"], self.actions)},
			"result": {key: name for key, name in zip(["z", "x", "c", "v"], self.results)},
		}

		self.events: list[EventRecord] = []
		self.filtered_indexes: list[int] = []
		self.current_player = ""
		self.current_action = ""
		self.current_result = ""
		self.is_playing = False
		self.duration_seconds = DEFAULT_DURATION_SECONDS
		self.video_capture: cv2.VideoCapture | None = None
		self.video_path: Path | None = None
		self.video_fps = 30.0
		self.video_frame_count = 0
		self.video_current_frame = 0
		self.playback_frame_accumulator = 0.0
		self.current_frame_photo: ImageTk.PhotoImage | None = None
		self.video_image_id: int | None = None
		self.playback_tick_ms = PLAYBACK_TICK_MS
		self.draw_mode = "none"
		self.draw_start: tuple[int, int] | None = None
		self.temp_draw_item: int | None = None
		self.draw_items: list[int] = []
		self.search_placeholder = "선수 / 액션 / 결과 검색"

		self._build_styles()
		self._build_layout()
		self._bind_events()
		self._draw_pitch_background()
		self._redraw_timeline()
		self.refresh_selection_state()
		self.refresh_logs()
		self.after(PLAYBACK_TICK_MS, self._tick)

	def _build_styles(self) -> None:
		self.font_default = tkfont.nametofont("TkDefaultFont")
		self.font_default.configure(family="Segoe UI", size=10)
		self.font_bold = tkfont.Font(family="Segoe UI", size=10, weight="bold")
		self.font_title = tkfont.Font(family="Segoe UI", size=13, weight="bold")
		self.font_sidebar = tkfont.Font(family="Segoe UI", size=18, weight="bold")
		self.font_video_title = tkfont.Font(family="Segoe UI", size=14, weight="bold")
		self.font_empty = tkfont.Font(family="Segoe UI", size=16, weight="bold")
		self.font_group = tkfont.Font(family="Segoe UI", size=11, weight="bold")
		self.font_tool = tkfont.Font(family="Segoe UI", size=12, weight="bold")
		self.font_canvas_small = tkfont.Font(family="Segoe UI", size=10, weight="bold")
		self.font_draw_text = tkfont.Font(family="Segoe UI", size=14, weight="bold")
		self.option_add("*Font", self.font_default)
		style = ttk.Style(self)
		try:
			style.theme_use("clam")
		except tk.TclError:
			pass
		style.configure("TFrame", background=VIDEO_BG)
		style.configure("Panel.TFrame", background=PANEL_BG)
		style.configure("Card.TFrame", background=CARD_BG)
		style.configure("Dark.TLabel", background=PANEL_BG, foreground=TEXT_MAIN)
		style.configure("Muted.TLabel", background=PANEL_BG, foreground=TEXT_MUTED)
		style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_MAIN)
		style.configure("TEntry", fieldbackground=CARD_BG, foreground=TEXT_MAIN)
		style.configure("TCombobox", fieldbackground=CARD_BG, foreground=TEXT_MAIN)
		style.configure(
			"Treeview",
			background=CARD_BG,
			foreground=TEXT_MAIN,
			fieldbackground=CARD_BG,
			rowheight=28,
			borderwidth=0,
		)
		style.configure(
			"Treeview.Heading",
			background=CARD_BG_2,
			foreground=TEXT_MAIN,
			relief="flat",
		)
		style.map("Treeview", background=[("selected", ACCENT_2)], foreground=[("selected", "#ffffff")])

	def _build_layout(self) -> None:
		self.grid_columnconfigure(0, weight=0)
		self.grid_columnconfigure(1, weight=1)
		self.grid_columnconfigure(2, weight=0)
		self.grid_rowconfigure(0, weight=1)

		self.sidebar = tk.Frame(self, bg="#0d1419", width=78)
		self.sidebar.grid(row=0, column=0, sticky="ns")
		self.sidebar.grid_propagate(False)

		self.main_area = tk.Frame(self, bg=VIDEO_BG)
		self.main_area.grid(row=0, column=1, sticky="nsew")
		self.main_area.grid_rowconfigure(1, weight=1)
		self.main_area.grid_columnconfigure(0, weight=1)

		self.right_area = tk.Frame(self, bg=PANEL_BG, width=400)
		self.right_area.grid(row=0, column=2, sticky="ns")
		self.right_area.grid_propagate(False)
		self.right_area.grid_rowconfigure(1, weight=1)
		self.right_area.grid_columnconfigure(0, weight=1)

		self._build_sidebar()
		self._build_header()
		self._build_video_panel()
		self._build_timeline_panel()
		self._build_quick_tag_panel()
		self._build_log_panel()
		self._build_status_bar()

	def _build_sidebar(self) -> None:
		tk.Label(self.sidebar, text="▶", bg="#0d1419", fg=ACCENT_2, font=self.font_sidebar).pack(pady=(18, 10))
		buttons = [
			("드로잉", self.toggle_draw_menu),
			("단축키", self.open_shortcuts),
			("오프셋", self.set_offset),
			("CSV", self.export_csv),
			("PDF", self.export_pdf),
			("초기화", self.clear_events),
		]
		for label, command in buttons:
			button = tk.Button(
				self.sidebar,
				text=label,
				command=command,
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_2,
				activeforeground="#ffffff",
				width=8,
				height=2,
			)
			button.pack(pady=8, padx=10, fill="x")

	def _build_header(self) -> None:
		header = tk.Frame(self.main_area, bg=VIDEO_BG, padx=10, pady=10)
		header.grid(row=0, column=0, sticky="ew")
		header.grid_columnconfigure(2, weight=1)

		mode_box = tk.Frame(header, bg=VIDEO_BG)
		mode_box.grid(row=0, column=0, sticky="w")
		self.mode_buttons: dict[str, tk.Button] = {}
		for index, mode in enumerate(["실시간 녹화", "동영상 불러오기"]):
			button = tk.Button(
				mode_box,
				text=mode,
				command=lambda selected=mode: self.set_mode(selected),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				padx=16,
				pady=8,
			)
			button.grid(row=0, column=index, padx=(0, 8))
			self.mode_buttons[mode] = button

		tk.Button(header, text="파일 불러오기", command=self.open_video_file, bg=ACCENT, fg="#081017", relief="flat", padx=16, pady=8).grid(row=0, column=1, padx=(10, 12))
		tk.Label(header, textvariable=self.file_var, bg=VIDEO_BG, fg=TEXT_MAIN, anchor="w").grid(row=0, column=2, sticky="ew")
		tk.Label(header, text="Dark Mode Analysis", bg=VIDEO_BG, fg=TEXT_MUTED).grid(row=0, column=3, padx=(12, 0))
		self._refresh_mode_buttons()

	def _build_video_panel(self) -> None:
		self.video_frame = tk.Frame(self.main_area, bg=VIDEO_BG, padx=10)
		self.video_frame.grid(row=1, column=0, sticky="nsew")
		self.video_frame.grid_rowconfigure(0, weight=1)
		self.video_frame.grid_columnconfigure(0, weight=1)

		self.video_canvas = tk.Canvas(self.video_frame, bg=VIDEO_BG, highlightthickness=0, height=460)
		self.video_canvas.grid(row=0, column=0, sticky="nsew")
		self.video_canvas.bind("<Configure>", lambda _event: self._draw_pitch_background())
		self.video_canvas.bind("<ButtonPress-1>", self._on_canvas_press)
		self.video_canvas.bind("<B1-Motion>", self._on_canvas_drag)
		self.video_canvas.bind("<ButtonRelease-1>", self._on_canvas_release)

		control_bar = tk.Frame(self.main_area, bg=VIDEO_BG, padx=10, pady=8)
		control_bar.grid(row=2, column=0, sticky="ew")
		control_bar.grid_columnconfigure(3, weight=1)

		tk.Button(control_bar, text="⟲ 3초", command=lambda: self.seek_relative(-3), bg=CARD_BG, fg=TEXT_MAIN, relief="flat", padx=14, pady=8).grid(row=0, column=0, padx=(0, 8))
		self.play_button = tk.Button(control_bar, text="재생", command=self.toggle_playback, bg=ACCENT, fg="#081017", relief="flat", padx=16, pady=8)
		self.play_button.grid(row=0, column=1, padx=(0, 8))
		tk.Button(control_bar, text="+3초", command=lambda: self.seek_relative(3), bg=CARD_BG, fg=TEXT_MAIN, relief="flat", padx=14, pady=8).grid(row=0, column=2, padx=(0, 12))
		tk.Label(control_bar, text="배속", bg=VIDEO_BG, fg=TEXT_MAIN).grid(row=0, column=3, sticky="e")
		for index, value in enumerate([0.5, 1.0, 2.0]):
			tk.Button(control_bar, text=f"{value:g}x", command=lambda speed=value: self.set_speed(speed), bg=CARD_BG, fg=TEXT_MAIN, relief="flat", padx=12, pady=8).grid(row=0, column=4 + index, padx=(8, 0))

		seek_bar_row = tk.Frame(self.main_area, bg=VIDEO_BG, padx=10, pady=6)
		seek_bar_row.grid(row=3, column=0, sticky="ew")
		seek_bar_row.grid_columnconfigure(0, weight=1)
		self.seek_scale = ttk.Scale(seek_bar_row, from_=0.0, to=self.duration_seconds, orient="horizontal", command=self._on_seek_change)
		self.seek_scale.grid(row=0, column=0, sticky="ew")
		self.seek_label = tk.Label(seek_bar_row, text="00:00 / 10:00", bg=VIDEO_BG, fg=TEXT_MAIN)
		self.seek_label.grid(row=0, column=1, padx=(10, 0))

	def _build_timeline_panel(self) -> None:
		timeline_wrap = tk.Frame(self.main_area, bg=VIDEO_BG, padx=10, pady=6)
		timeline_wrap.grid(row=4, column=0, sticky="ew")
		timeline_wrap.grid_columnconfigure(0, weight=1)
		self.timeline_canvas = tk.Canvas(timeline_wrap, bg=CARD_BG, highlightthickness=0, height=76)
		self.timeline_canvas.grid(row=0, column=0, sticky="ew")
		self.timeline_canvas.bind("<Configure>", lambda _event: self._redraw_timeline())
		self.timeline_canvas.bind("<Button-1>", self._on_timeline_click)

	def _build_quick_tag_panel(self) -> None:
		panel = tk.Frame(self.right_area, bg=PANEL_BG, padx=12, pady=12)
		panel.grid(row=0, column=0, sticky="ew")
		panel.grid_columnconfigure(0, weight=1)

		title_row = tk.Frame(panel, bg=PANEL_BG)
		title_row.grid(row=0, column=0, sticky="ew")
		tk.Label(title_row, text="Quick Tagging", bg=PANEL_BG, fg=TEXT_MAIN, font=self.font_title).pack(side="left")
		self.selection_label = tk.Label(title_row, text="선수 - 액션 - 결과", bg=PANEL_BG, fg=TEXT_MUTED)
		self.selection_label.pack(side="right")

		self.player_box = self._build_button_group(panel, "선수", self.players, 1, "player")
		self.action_box = self._build_button_group(panel, "액션", self.actions, 2, "action")
		self.result_box = self._build_button_group(panel, "결과", self.results, 3, "result")

	def _build_button_group(self, parent: tk.Widget, title: str, items: list[str], row_index: int, category: str) -> dict[str, tk.Button]:
		box = tk.Frame(parent, bg=CARD_BG, padx=10, pady=10)
		box.grid(row=row_index, column=0, sticky="ew", pady=(12, 0))
		box.grid_columnconfigure(0, weight=1)
		tk.Label(box, text=title, bg=CARD_BG, fg=TEXT_MAIN, font=self.font_group).grid(row=0, column=0, sticky="w", pady=(0, 8))

		button_frame = tk.Frame(box, bg=CARD_BG)
		button_frame.grid(row=1, column=0, sticky="ew")
		button_map: dict[str, tk.Button] = {}
		columns = 3 if category in {"player", "action"} else 2
		for index, item in enumerate(items):
			button = tk.Button(
				button_frame,
				text=item,
				command=lambda selected=item, kind=category: self.select_tag(kind, selected),
				bg="#1b2c37",
				fg=TEXT_MAIN,
				relief="flat",
				padx=10,
				pady=8,
				wraplength=110,
				justify="center",
			)
			button.grid(row=index // columns, column=index % columns, padx=4, pady=4, sticky="ew")
			button_map[item] = button
			button_frame.grid_columnconfigure(index % columns, weight=1)
		return button_map

	def _build_log_panel(self) -> None:
		panel = tk.Frame(self.right_area, bg=PANEL_BG, padx=12, pady=12)
		panel.grid(row=1, column=0, sticky="nsew")
		panel.grid_rowconfigure(2, weight=1)
		panel.grid_columnconfigure(0, weight=1)

		header = tk.Frame(panel, bg=PANEL_BG)
		header.grid(row=0, column=0, sticky="ew")
		header.grid_columnconfigure(0, weight=1)
		tk.Label(header, text="이벤트 로그", bg=PANEL_BG, fg=TEXT_MAIN, font=self.font_title).grid(row=0, column=0, sticky="w")
		tk.Label(header, textvariable=self.summary_var, bg=PANEL_BG, fg=TEXT_MUTED).grid(row=1, column=0, sticky="w", pady=(2, 0))

		filter_row = tk.Frame(panel, bg=PANEL_BG)
		filter_row.grid(row=1, column=0, sticky="ew", pady=(10, 8))
		filter_row.grid_columnconfigure(0, weight=1)
		self.search_entry = ttk.Entry(filter_row, textvariable=self.search_var)
		self.search_entry.grid(row=0, column=0, sticky="ew")
		self.search_entry.insert(0, self.search_placeholder)
		self.search_entry.bind("<FocusIn>", lambda _event: self._clear_placeholder(self.search_entry))
		self.search_entry.bind("<FocusOut>", lambda _event: self._restore_placeholder(self.search_entry))
		self.search_var.trace_add("write", lambda *_args: self.refresh_logs())

		self.filter_box = ttk.Combobox(filter_row, textvariable=self.filter_var, values=["전체", "성공", "실패", "파울 유도", "차단"], state="readonly", width=10)
		self.filter_box.grid(row=0, column=1, padx=(8, 0))
		self.filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_logs())

		table_wrap = tk.Frame(panel, bg=PANEL_BG)
		table_wrap.grid(row=2, column=0, sticky="nsew")
		table_wrap.grid_rowconfigure(0, weight=1)
		table_wrap.grid_columnconfigure(0, weight=1)

		columns = ("time", "player", "action", "result")
		self.log_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", selectmode="browse")
		self.log_tree.heading("time", text="시간")
		self.log_tree.heading("player", text="선수")
		self.log_tree.heading("action", text="액션")
		self.log_tree.heading("result", text="결과")
		self.log_tree.column("time", width=72, anchor="center")
		self.log_tree.column("player", width=120, anchor="w")
		self.log_tree.column("action", width=90, anchor="w")
		self.log_tree.column("result", width=90, anchor="center")
		self.log_tree.grid(row=0, column=0, sticky="nsew")
		self.log_tree.bind("<Double-1>", self.jump_to_selected_log)

		scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.log_tree.yview)
		self.log_tree.configure(yscrollcommand=scrollbar.set)
		scrollbar.grid(row=0, column=1, sticky="ns")

		footer = tk.Frame(panel, bg=PANEL_BG)
		footer.grid(row=3, column=0, sticky="ew", pady=(10, 0))
		tk.Button(footer, text="CSV로 내보내기", command=self.export_csv, bg=ACCENT_2, fg="#081017", relief="flat", padx=14, pady=8).pack(side="left")
		tk.Button(footer, text="PDF 리포트", command=self.export_pdf, bg=CARD_BG_2, fg=TEXT_MAIN, relief="flat", padx=14, pady=8).pack(side="left", padx=8)

	def _build_status_bar(self) -> None:
		bar = tk.Frame(self, bg="#0a1014", height=28)
		bar.grid(row=1, column=0, columnspan=3, sticky="ew")
		bar.grid_propagate(False)
		tk.Label(bar, textvariable=self.status_var, bg="#0a1014", fg=TEXT_MUTED, anchor="w").pack(fill="x", padx=12)

	def _bind_events(self) -> None:
		self.bind_all("<space>", lambda _event: self.toggle_playback())
		self.bind_all("<Left>", lambda _event: self.seek_relative(-3))
		self.bind_all("<Right>", lambda _event: self.seek_relative(3))
		self.bind_all("<Control-o>", lambda _event: self.open_video_file())
		self.bind_all("<Control-s>", lambda _event: self.export_csv())
		self.bind_all("<Key>", self._handle_keypress)

	def _handle_keypress(self, event: tk.Event) -> None:
		key = (event.char or "").lower()
		if not key:
			return
		for category in ("player", "action", "result"):
			mapping = self.shortcut_map.get(category, {})
			if key in mapping:
				self.select_tag(category, mapping[key])
				return

	def _clear_placeholder(self, entry: ttk.Entry) -> None:
		if entry.get() == self.search_placeholder:
			entry.delete(0, "end")
			self.search_var.set("")

	def _restore_placeholder(self, entry: ttk.Entry) -> None:
		if not entry.get():
			entry.insert(0, self.search_placeholder)
			self.search_var.set("")

	def _refresh_mode_buttons(self) -> None:
		for mode, button in self.mode_buttons.items():
			if mode == self.mode_var.get():
				button.configure(bg=ACCENT_2, fg="#081017")
			else:
				button.configure(bg=CARD_BG, fg=TEXT_MAIN)

	def set_mode(self, mode: str) -> None:
		self.mode_var.set(mode)
		self._refresh_mode_buttons()
		self.refresh_status(f"모드 변경: {mode}")

	def open_video_file(self) -> None:
		path = filedialog.askopenfilename(
			title="분석할 동영상 선택",
			filetypes=[
				("Video files", "*.mp4 *.mkv *.mov *.avi *.webm"),
				("All files", "*.*"),
			],
		)
		if not path:
			return
		file_path = Path(path)
		self._release_video()
		capture = cv2.VideoCapture(str(file_path))
		if not capture.isOpened():
			messagebox.showerror("동영상 불러오기", "선택한 파일을 열 수 없습니다.", parent=self)
			return

		self.video_capture = capture
		self.video_path = file_path
		self.video_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
		self.video_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
		self.playback_tick_ms = max(15, int(round(1000 / max(1.0, self.video_fps))))
		self.playback_frame_accumulator = 0.0
		if self.video_frame_count > 0 and self.video_fps > 0:
			self.duration_seconds = self.video_frame_count / self.video_fps
		else:
			self.duration_seconds = DEFAULT_DURATION_SECONDS
		self.seek_scale.configure(to=self.duration_seconds)
		self.time_var.set(0.0)
		self.video_current_frame = 0
		self.file_var.set(file_path.name)
		self.refresh_status(f"파일 선택됨: {file_path.name} · {self.video_fps:.1f}fps")
		self.current_time_reset()
		self._render_video_view()

	def _release_video(self) -> None:
		if self.video_capture is not None:
			self.video_capture.release()
		self.video_capture = None
		self.video_path = None
		self.video_fps = 30.0
		self.video_frame_count = 0
		self.video_current_frame = 0
		self.playback_frame_accumulator = 0.0
		self.current_frame_photo = None
		self.playback_tick_ms = PLAYBACK_TICK_MS
		if self.video_image_id is not None and self.video_canvas.winfo_exists():
			self.video_canvas.delete(self.video_image_id)
			self.video_image_id = None

	def refresh_status(self, message: str) -> None:
		self.status_var.set(message)

	def current_time_reset(self) -> None:
		self.time_var.set(0.0)
		self.seek_scale.set(0.0)
		self._update_time_ui()

	def toggle_playback(self) -> None:
		self.is_playing = not self.is_playing
		self.play_button.configure(text="일시정지" if self.is_playing else "재생")
		self.refresh_status("재생 중" if self.is_playing else "정지됨")

	def set_speed(self, speed: float) -> None:
		self.speed_var.set(speed)
		self.refresh_status(f"배속 {speed:g}x")
		self._draw_pitch_background()

	def seek_relative(self, delta_seconds: float) -> None:
		self.time_var.set(clamp(self.time_var.get() + delta_seconds, 0.0, self.duration_seconds))
		self.seek_scale.set(self.time_var.get())
		self._update_time_ui()

	def _on_seek_change(self, value: str) -> None:
		self.time_var.set(clamp(float(value), 0.0, self.duration_seconds))
		self._update_time_ui()
		self._render_video_view()

	def _update_time_ui(self) -> None:
		current = self.time_var.get()
		self.seek_label.configure(text=f"{format_time(current)} / {format_time(self.duration_seconds)}")
		self._redraw_timeline()

	def _tick(self) -> None:
		if self.is_playing:
			self._advance_playback_frame()
		self.after(self.playback_tick_ms, self._tick)

	def _display_video_frame(self, frame) -> None:
		canvas = self.video_canvas
		if not canvas.winfo_exists():
			return
		width = max(1, canvas.winfo_width())
		height = max(1, canvas.winfo_height())
		canvas.delete("all")

		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
		image = Image.fromarray(frame_rgb)
		image.thumbnail((width, height), Image.Resampling.LANCZOS)
		photo = ImageTk.PhotoImage(image)
		self.current_frame_photo = photo

		offset_x = (width - photo.width()) // 2
		offset_y = (height - photo.height()) // 2
		canvas.create_rectangle(0, 0, width, height, fill=VIDEO_BG, outline=VIDEO_BG)
		canvas.create_image(offset_x, offset_y, image=photo, anchor="nw")
		canvas.create_text(16, 16, text="스마트 비디오 플레이어", anchor="nw", fill=TEXT_MAIN, font=self.font_video_title)
		canvas.create_text(16, 44, text=self.file_var.get(), anchor="nw", fill=TEXT_MUTED)
		canvas.create_text(width - 16, 16, text=f"x{self.speed_var.get():g} · 오프셋 {self.offset_var.get():+g}s", anchor="ne", fill=TEXT_MAIN)
		canvas.create_text(width - 16, 44, text=f"현재 {format_time(self.time_var.get())}", anchor="ne", fill=TEXT_MUTED)

	def _advance_playback_frame(self) -> None:
		if self.video_capture is None:
			return

		self.playback_frame_accumulator += self.speed_var.get()
		frames_to_read = int(self.playback_frame_accumulator)
		if frames_to_read <= 0:
			return

		self.playback_frame_accumulator -= frames_to_read
		latest_frame = None
		for _ in range(frames_to_read):
			success, frame = self.video_capture.read()
			if not success or frame is None:
				self.is_playing = False
				self.play_button.configure(text="재생")
				self.refresh_status("재생 종료")
				return
			latest_frame = frame
			self.video_current_frame += 1

		if latest_frame is None:
			return

		self.time_var.set(min(self.video_current_frame / max(1.0, self.video_fps), self.duration_seconds))
		if self.video_frame_count > 0 and self.video_current_frame >= self.video_frame_count:
			self.is_playing = False
			self.play_button.configure(text="재생")
			self.refresh_status("재생 종료")
		self.seek_scale.set(self.time_var.get())
		self._update_time_ui()
		self._display_video_frame(latest_frame)

	def select_tag(self, category: str, value: str) -> None:
		if category == "player":
			self.current_player = value
		elif category == "action":
			self.current_action = value
		else:
			self.current_result = value
		self.refresh_selection_state()
		if self.current_player and self.current_action and self.current_result:
			self.add_event()

	def refresh_selection_state(self) -> None:
		selection_text = f"{self.current_player or '선수'} - {self.current_action or '액션'} - {self.current_result or '결과'}"
		self.selection_label.configure(text=selection_text)
		self._refresh_button_states()

	def _refresh_button_states(self) -> None:
		for value, button in self.player_box.items():
			button.configure(bg=ACCENT_2 if value == self.current_player else "#1b2c37")
		for value, button in self.action_box.items():
			button.configure(bg=ACCENT_2 if value == self.current_action else "#1b2c37")
		for value, button in self.result_box.items():
			button.configure(bg=RESULT_COLORS.get(value, CARD_BG_2) if value == self.current_result else "#1b2c37")

	def add_event(self) -> None:
		record = EventRecord(
			time_seconds=clamp(self.time_var.get() + self.offset_var.get(), 0.0, self.duration_seconds),
			player=self.current_player,
			action=self.current_action,
			result=self.current_result,
		)
		self.events.append(record)
		self.current_player = ""
		self.current_action = ""
		self.current_result = ""
		self.refresh_selection_state()
		self.refresh_logs()
		self._redraw_timeline()
		self.refresh_status(f"이벤트 기록: {record.player} / {record.action} / {record.result} @ {format_time(record.time_seconds)}")

	def clear_events(self) -> None:
		if self.events and not messagebox.askyesno("초기화", "기록된 이벤트를 모두 삭제할까요?", parent=self):
			return
		self.events.clear()
		self.refresh_logs()
		self._redraw_timeline()
		self.refresh_status("이벤트가 초기화되었습니다")

	def refresh_logs(self) -> None:
		search_text = self.search_var.get().strip().lower()
		if search_text == self.search_placeholder.lower():
			search_text = ""
		result_filter = self.filter_var.get().strip()
		self.log_tree.delete(*self.log_tree.get_children())
		self.filtered_indexes.clear()

		for index, record in enumerate(self.events):
			if result_filter != "전체" and record.result != result_filter:
				continue
			haystack = f"{format_time(record.time_seconds)} {record.player} {record.action} {record.result}".lower()
			if search_text and search_text not in haystack:
				continue
			self.filtered_indexes.append(index)
			self.log_tree.insert(
				"",
				"end",
				iid=str(index),
				values=(format_time(record.time_seconds), record.player, record.action, record.result),
				tags=(record.result,),
			)

		total = len(self.events)
		success_count = sum(1 for record in self.events if record.result == "성공")
		rate_text = f"{(success_count / total * 100):.1f}%" if total else "-"
		self.summary_var.set(f"이벤트 {total}개 · 성공률 {rate_text}")

	def jump_to_selected_log(self, _event: tk.Event) -> None:
		selection = self.log_tree.selection()
		if not selection:
			return
		index = int(selection[0])
		if index >= len(self.events):
			return
		self.time_var.set(self.events[index].time_seconds)
		self.seek_scale.set(self.time_var.get())
		self._update_time_ui()
		self._render_video_view()
		self.refresh_status(f"이동: {format_time(self.events[index].time_seconds)}")

	def _on_timeline_click(self, event: tk.Event) -> None:
		width = max(1, self.timeline_canvas.winfo_width())
		position = clamp(event.x / width * self.duration_seconds, 0.0, self.duration_seconds)
		self.time_var.set(position)
		self.seek_scale.set(position)
		self._update_time_ui()
		self._render_video_view()

	def _redraw_timeline(self) -> None:
		canvas = self.timeline_canvas
		if not canvas.winfo_exists():
			return
		width = max(1, canvas.winfo_width())
		height = max(1, canvas.winfo_height())
		canvas.delete("all")
		canvas.create_rectangle(0, 0, width, height, fill=CARD_BG, outline=CARD_BG)
		bar_y = height / 2 + 7
		canvas.create_line(20, bar_y, width - 20, bar_y, fill="#314452", width=6)
		current_x = 20 + (width - 40) * (self.time_var.get() / max(1.0, self.duration_seconds))
		canvas.create_line(20, bar_y, current_x, bar_y, fill=ACCENT, width=6)
		canvas.create_oval(current_x - 7, bar_y - 7, current_x + 7, bar_y + 7, fill=ACCENT, outline="")
		canvas.create_text(20, 18, text="타임라인", anchor="w", fill=TEXT_MAIN, font=self.font_canvas_small)
		canvas.create_text(width - 20, 18, text=f"현재 {format_time(self.time_var.get())}", anchor="e", fill=TEXT_MUTED)
		for record in self.events:
			x = 20 + (width - 40) * (record.time_seconds / max(1.0, self.duration_seconds))
			color = RESULT_COLORS.get(record.result, ACCENT_2)
			canvas.create_oval(x - 4, bar_y - 16, x + 4, bar_y - 8, fill=color, outline="")

	def _draw_pitch_background(self) -> None:
		if self.video_capture is not None:
			self._render_video_view()
			return

		canvas = self.video_canvas
		if not canvas.winfo_exists():
			return
		width = max(1, canvas.winfo_width())
		height = max(1, canvas.winfo_height())
		canvas.delete("background")
		canvas.delete("hud")

		canvas.create_rectangle(0, 0, width, height, fill=VIDEO_BG, outline=VIDEO_BG, tags=("background",))
		inset_x = 34
		inset_y = 28
		pitch_left = inset_x
		pitch_top = inset_y
		pitch_right = width - inset_x
		pitch_bottom = height - inset_y
		pitch_width = pitch_right - pitch_left
		pitch_height = pitch_bottom - pitch_top

		stripe_count = 8
		for index in range(stripe_count):
			stripe_left = pitch_left + pitch_width * index / stripe_count
			stripe_right = pitch_left + pitch_width * (index + 1) / stripe_count
			color = "#153120" if index % 2 == 0 else "#183826"
			canvas.create_rectangle(stripe_left, pitch_top, stripe_right, pitch_bottom, fill=color, outline=color, tags=("background",))

		canvas.create_rectangle(pitch_left, pitch_top, pitch_right, pitch_bottom, outline="#7bbd7b", width=3, tags=("background",))
		canvas.create_line((pitch_left + pitch_right) / 2, pitch_top, (pitch_left + pitch_right) / 2, pitch_bottom, fill="#7bbd7b", width=2, tags=("background",))
		canvas.create_oval(
			pitch_left + pitch_width * 0.42,
			pitch_top + pitch_height * 0.32,
			pitch_left + pitch_width * 0.58,
			pitch_top + pitch_height * 0.68,
			outline="#7bbd7b",
			width=2,
			tags=("background",),
		)
		canvas.create_rectangle(pitch_left + 14, pitch_top + pitch_height * 0.32, pitch_left + 112, pitch_top + pitch_height * 0.68, outline="#7bbd7b", width=2, tags=("background",))
		canvas.create_rectangle(pitch_right - 112, pitch_top + pitch_height * 0.32, pitch_right - 14, pitch_top + pitch_height * 0.68, outline="#7bbd7b", width=2, tags=("background",))
		canvas.create_oval(pitch_left + 6, (pitch_top + pitch_bottom) / 2 - 54, pitch_left + 80, (pitch_top + pitch_bottom) / 2 + 54, outline="#7bbd7b", width=2, tags=("background",))
		canvas.create_oval(pitch_right - 80, (pitch_top + pitch_bottom) / 2 - 54, pitch_right - 6, (pitch_top + pitch_bottom) / 2 + 54, outline="#7bbd7b", width=2, tags=("background",))

		file_name = self.file_var.get()
		canvas.create_text(16, 16, text="스마트 비디오 플레이어", anchor="nw", fill=TEXT_MAIN, font=self.font_video_title, tags=("hud",))
		canvas.create_text(16, 44, text=file_name, anchor="nw", fill=TEXT_MUTED, tags=("hud",))
		canvas.create_text(width - 16, 16, text=f"x{self.speed_var.get():g} · 오프셋 {self.offset_var.get():+g}s", anchor="ne", fill=TEXT_MAIN, tags=("hud",))
		canvas.create_text(width - 16, 44, text=f"현재 {format_time(self.time_var.get())}", anchor="ne", fill=TEXT_MUTED, tags=("hud",))
		if not self.events:
			canvas.create_text(
				width / 2,
				height / 2,
				text="동영상을 불러오고 태깅을 시작하세요",
				fill="#d2e1ea",
				font=self.font_empty,
				tags=("hud",),
			)

	def _render_video_view(self) -> None:
		canvas = self.video_canvas
		if not canvas.winfo_exists():
			return
		width = max(1, canvas.winfo_width())
		height = max(1, canvas.winfo_height())
		canvas.delete("all")

		if self.video_capture is None:
			self._draw_pitch_background()
			return

		frame_index = int(round(self.time_var.get() * self.video_fps))
		frame_index = max(0, min(frame_index, max(0, self.video_frame_count - 1)))
		if frame_index != self.video_current_frame:
			self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
			self.video_current_frame = frame_index
			self.playback_frame_accumulator = 0.0

		success, frame = self.video_capture.read()
		if not success or frame is None:
			self._draw_pitch_background()
			return

		self.video_current_frame = frame_index + 1
		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
		image = Image.fromarray(frame_rgb)
		image.thumbnail((width, height), Image.Resampling.LANCZOS)
		photo = ImageTk.PhotoImage(image)
		self.current_frame_photo = photo

		offset_x = (width - photo.width()) // 2
		offset_y = (height - photo.height()) // 2
		canvas.create_rectangle(0, 0, width, height, fill=VIDEO_BG, outline=VIDEO_BG)
		canvas.create_image(offset_x, offset_y, image=photo, anchor="nw")
		canvas.create_text(16, 16, text="스마트 비디오 플레이어", anchor="nw", fill=TEXT_MAIN, font=self.font_video_title)
		canvas.create_text(16, 44, text=self.file_var.get(), anchor="nw", fill=TEXT_MUTED)
		canvas.create_text(width - 16, 16, text=f"x{self.speed_var.get():g} · 오프셋 {self.offset_var.get():+g}s", anchor="ne", fill=TEXT_MAIN)
		canvas.create_text(width - 16, 44, text=f"현재 {format_time(self.time_var.get())}", anchor="ne", fill=TEXT_MUTED)
		if self.draw_mode in {"arrow", "circle", "text"}:
			canvas.create_text(width - 16, height - 18, text=f"드로잉: {self.draw_mode}", anchor="se", fill="#ffffff")

	def close_video(self) -> None:
		self._release_video()
		self.duration_seconds = DEFAULT_DURATION_SECONDS
		self.seek_scale.configure(to=self.duration_seconds)
		self.current_time_reset()
		self._draw_pitch_background()

	def toggle_draw_menu(self) -> None:
		menu = tk.Toplevel(self)
		menu.title("드로잉 도구")
		menu.configure(bg=PANEL_BG)
		menu.resizable(False, False)
		menu.transient(self)
		menu.grab_set()

		tk.Label(menu, text="드로잉 툴", bg=PANEL_BG, fg=TEXT_MAIN, font=self.font_tool).pack(anchor="w", padx=16, pady=(14, 6))
		choices = [
			("끄기", "none"),
			("화살표", "arrow"),
			("원", "circle"),
			("텍스트", "text"),
			("그림 모두 지우기", "clear"),
		]
		for label, value in choices:
			tk.Button(
				menu,
				text=label,
				command=lambda selected=value: self.set_draw_mode(selected, menu),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				padx=12,
				pady=8,
			).pack(fill="x", padx=16, pady=5)

	def set_draw_mode(self, mode: str, dialog: tk.Toplevel | None = None) -> None:
		if mode == "clear":
			if self.temp_draw_item is not None:
				self.video_canvas.delete(self.temp_draw_item)
				self.temp_draw_item = None
			for item in self.draw_items:
				self.video_canvas.delete(item)
			self.draw_items.clear()
			self.refresh_status("도형이 초기화되었습니다")
		else:
			self.draw_mode = mode
			self.refresh_status(f"드로잉 모드: {mode}")
		if dialog is not None:
			dialog.destroy()
		self._draw_pitch_background()

	def _on_canvas_press(self, event: tk.Event) -> None:
		if self.draw_mode == "none":
			return
		self.draw_start = (event.x, event.y)
		if self.draw_mode == "text":
			text = simpledialog.askstring("텍스트 입력", "표시할 텍스트를 입력하세요.", parent=self)
			if text:
				item = self.video_canvas.create_text(event.x, event.y, text=text, fill="#ffffff", font=self.font_draw_text, tags=("drawing",))
				self.draw_items.append(item)
			self.draw_start = None

	def _on_canvas_drag(self, event: tk.Event) -> None:
		if self.draw_mode not in {"arrow", "circle"} or not self.draw_start:
			return
		if self.temp_draw_item is not None:
			self.video_canvas.delete(self.temp_draw_item)
		start_x, start_y = self.draw_start
		if self.draw_mode == "arrow":
			self.temp_draw_item = self.video_canvas.create_line(start_x, start_y, event.x, event.y, arrow=tk.LAST, fill="#ffe082", width=3, tags=("drawing",))
		else:
			self.temp_draw_item = self.video_canvas.create_oval(start_x, start_y, event.x, event.y, outline="#ffe082", width=3, tags=("drawing",))

	def _on_canvas_release(self, _event: tk.Event) -> None:
		if self.draw_mode not in {"arrow", "circle"} or not self.draw_start:
			return
		if self.temp_draw_item is not None:
			self.draw_items.append(self.temp_draw_item)
			self.temp_draw_item = None
		self.draw_start = None

	def open_shortcuts(self) -> None:
		ShortcutEditor(self)

	def set_offset(self) -> None:
		value = simpledialog.askfloat("오프셋 설정", "기록 오프셋을 초 단위로 입력하세요.", initialvalue=self.offset_var.get(), parent=self)
		if value is None:
			return
		self.offset_var.set(value)
		self.refresh_status(f"오프셋 설정: {value:+g}s")
		self._draw_pitch_background()

	def _build_report_lines(self) -> list[str]:
		lines = [
			f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
			f"파일: {self.file_var.get()}",
			f"모드: {self.mode_var.get()}",
			f"오프셋: {self.offset_var.get():+g}s",
			f"배속: {self.speed_var.get():g}x",
			f"총 이벤트: {len(self.events)}",
			"",
			"이벤트 목록",
		]
		for index, record in enumerate(self.events, start=1):
			lines.append(f"{index:03d}. {format_time(record.time_seconds)} | {record.player} | {record.action} | {record.result}")
		return lines

	def export_csv(self) -> None:
		if not self.events:
			messagebox.showinfo("CSV 내보내기", "내보낼 이벤트가 없습니다.", parent=self)
			return
		default_name = f"football_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
		path = filedialog.asksaveasfilename(
			title="CSV 저장",
			defaultextension=".csv",
			initialfile=default_name,
			filetypes=[("CSV files", "*.csv")],
		)
		if not path:
			return
		with open(path, "w", newline="", encoding="utf-8-sig") as file_handle:
			writer = csv.writer(file_handle)
			writer.writerow(["time", "player", "action", "result"])
			for record in self.events:
				writer.writerow([format_time(record.time_seconds), record.player, record.action, record.result])
		self.refresh_status(f"CSV 저장 완료: {Path(path).name}")

	def export_pdf(self) -> None:
		if not self.events:
			messagebox.showinfo("PDF 리포트", "리포트를 만들 이벤트가 없습니다.", parent=self)
			return
		default_name = f"football_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
		path = filedialog.asksaveasfilename(
			title="PDF 저장",
			defaultextension=".pdf",
			initialfile=default_name,
			filetypes=[("PDF files", "*.pdf")],
		)
		if not path:
			return
		lines = self._build_report_lines()
		build_simple_pdf(lines, Path(path))
		self.refresh_status(f"PDF 저장 완료: {Path(path).name}")


def main() -> None:
	app = FootballAnalysisApp()
	app.mainloop()


if __name__ == "__main__":
	main()
