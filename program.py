from __future__ import annotations


import csv
import ctypes
import importlib
import re
import sys
import time
import unicodedata
import subprocess
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk
import json
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import Request, urlopen

try:
	import cv2
except ImportError:  # pragma: no cover - depends on local environment
	cv2 = None

try:
	from PIL import Image, ImageTk
except ImportError:  # pragma: no cover - depends on local environment
	Image = None
	ImageTk = None

try:
	_ffpyplayer_player = importlib.import_module("ffpyplayer.player")
	MediaPlayer = getattr(_ffpyplayer_player, "MediaPlayer", None)
except Exception:  # pragma: no cover - depends on local environment
	MediaPlayer = None


VIDEO_FILETYPES = [
	("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.wmv *.flv"),
	("All files", "*.*"),
]
DEFAULT_VIDEO_INITIAL_DIR = Path(r"C:\Users\피콜록콜록\OneDrive\바탕 화면\새 폴더\Football")

WINDOW_BG = "#0c1419"
PANEL_BG = "#101920"
CARD_BG = "#16232d"
TEXT_MAIN = "#edf3f7"
TEXT_MUTED = "#93a8b8"
ACCENT = "#1dbf73"
ACCENT_DARK = "#15915a"
MAX_DECODE_FRAMES_PER_TICK = 8

ACTION_RESULT_OPTIONS: dict[str, list[str]] = {
	"패스": ["기가막히는패스", "깔끔한원터치패스", "좋은패스", "패스미스", "좋은전환패스", "전환패스실패", "좋은롱패스", "롱패스실패", "판단미스"],
	"크로스": ["좋은크로스", "똥크로스", "에라이크로스"],
	"골": ["원더골", "헤딩골", "좋은마무리", "그냥골"],
	"슈팅": ["좋은슈팅", "아쉬운마무리"],
	"드리블": ["좋은드리블", "무리한드리블"],
	"터치": ["좋은터치", "아쉬운터치", "실수"],
	"수비": ["좋은수비", "아쉬운수비", "좋은인터셉트", "슈퍼태클", "좋은태클"],
	"침투": ["좋은침투", "좋은오프더볼"],
	"온더볼": ["볼을많이끎"],
	"활동량": ["많이뜀"],
	"세트피스": ["롱쓰로인골", "좋은킥", "코너킥골", "위협적인코너킥", "프리킥골", "위협적인프리킥", "패널티킥성공", "패널티킥실패"],
	"북마크": ["한마디 메모"],
}
ACTION_OPTIONS = list(ACTION_RESULT_OPTIONS.keys())

PLAYER_OPTIONS_HOME = []
PLAYER_OPTIONS_AWAY = []
BENCH_OPTIONS_HOME = []
BENCH_OPTIONS_AWAY = []
PLAYER_ID_MAP_HOME = {}
PLAYER_ID_MAP_AWAY = {}
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
THUMBNAIL_ICON_PATH = ASSETS_DIR / "thumbnail.ico"


def set_windows_app_user_model_id(app_id: str) -> None:
	if not app_id:
		return
	if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "shell32"):
		try:
			ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
		except Exception:
			pass


def apply_windows_taskbar_icon(window: tk.Tk, icon_path: Path) -> None:
	if not hasattr(ctypes, "windll") or not hasattr(ctypes.windll, "user32"):
		return
	if not icon_path.exists():
		return
	try:
		window.update_idletasks()
		hwnd = window.winfo_id()
		user32 = ctypes.windll.user32
		image_icon = 1
		wm_seticon = 0x0080
		icon_small = 0
		icon_big = 1
		lr_loadfromfile = 0x0010
		lr_defaultsize = 0x0040
		hicon_big = user32.LoadImageW(None, str(icon_path), image_icon, 0, 0, lr_loadfromfile | lr_defaultsize)
		hicon_small = user32.LoadImageW(None, str(icon_path), image_icon, 16, 16, lr_loadfromfile | lr_defaultsize)
		if hicon_big:
			user32.SendMessageW(hwnd, wm_seticon, icon_big, hicon_big)
		if hicon_small:
			user32.SendMessageW(hwnd, wm_seticon, icon_small, hicon_small)
	except Exception:
		pass


@dataclass
class TimelineRecord:
	time_seconds: float
	team: str
	jersey_number: str
	player_name: str
	action: str
	period_label: str = ""
	player_id: str = ""
	result: str = ""
	sub_out_jersey_number: str = ""
	sub_out_player_id: str = ""
	sub_out_player_name: str = ""
	sub_in_jersey_number: str = ""
	sub_in_player_id: str = ""
	sub_in_player_name: str = ""


class RecordDialog(simpledialog.Dialog):
	def __init__(self, parent: tk.Misc) -> None:
		self.team_name = "홈"
		self.jersey_number = ""
		self.player_name = ""
		self.action_name = ""
		super().__init__(parent, title="현재 시점 기록")

	def body(self, master: tk.Misc) -> tk.Widget | None:
		tk.Label(master, text="지금 보고 있는 시점에 남길 기록을 입력하세요.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
		tk.Label(master, text="팀").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
		self.team_combo = ttk.Combobox(master, values=["홈", "어웨이"], width=25, state="readonly")
		self.team_combo.grid(row=1, column=1, sticky="ew", pady=4)
		self.team_combo.set("홈")
		tk.Label(master, text="등번호").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
		self.jersey_entry = ttk.Entry(master, width=28)
		self.jersey_entry.grid(row=2, column=1, sticky="ew", pady=4)
		tk.Label(master, text="선수 이름").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=4)
		self.player_entry = ttk.Entry(master, width=28)
		self.player_entry.grid(row=3, column=1, sticky="ew", pady=4)
		tk.Label(master, text="행위").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=4)
		self.action_combo = ttk.Combobox(master, values=ACTION_OPTIONS, width=25, state="readonly")
		self.action_combo.grid(row=4, column=1, sticky="ew", pady=4)
		self.action_combo.set(ACTION_OPTIONS[0])
		master.columnconfigure(1, weight=1)
		return self.player_entry

	def validate(self) -> bool:
		team = self.team_combo.get().strip()
		jersey = self.jersey_entry.get().strip()
		player = self.player_entry.get().strip()
		action = self.action_combo.get().strip()
		if team not in ("홈", "어웨이"):
			messagebox.showwarning("행위 기록", "팀을 선택하세요.", parent=self)
			return False
		if not player:
			messagebox.showwarning("행위 기록", "선수 이름을 입력하세요.", parent=self)
			return False
		if not action:
			messagebox.showwarning("행위 기록", "행위를 선택하세요.", parent=self)
			return False
		self.team_name = team
		self.jersey_number = jersey
		self.player_name = player
		self.action_name = action
		return True


def clamp(value: float, minimum: float, maximum: float) -> float:
	return max(minimum, min(maximum, value))


def get_default_video_initial_dir() -> str:
	if DEFAULT_VIDEO_INITIAL_DIR.exists():
		return str(DEFAULT_VIDEO_INITIAL_DIR)
	return str(Path.cwd())


def format_time(seconds: float) -> str:
	seconds = max(0, int(seconds))
	hours, remainder = divmod(seconds, 3600)
	minutes, secs = divmod(remainder, 60)
	if hours:
		return f"{hours:02d}:{minutes:02d}:{secs:02d}"
	return f"{minutes:02d}:{secs:02d}"


def format_time_for_csv(seconds: float) -> str:
	# Force a stable HH:MM:SS representation so spreadsheet tools do not reinterpret MM:SS values.
	seconds = max(0, int(seconds))
	hours, remainder = divmod(seconds, 3600)
	minutes, secs = divmod(remainder, 60)
	return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_timeline_offset_input(value: str) -> float:
	text = value.strip()
	if not text:
		raise ValueError("빈 값입니다.")

	if text.isdigit():
		return float(int(text) * 60)

	normalized_colon = re.sub(r"\s*:\s*", ":", text)
	parts = normalized_colon.split(":")
	if len(parts) == 2 and all(part.strip().isdigit() for part in parts):
		minutes = int(parts[0].strip())
		seconds = int(parts[1].strip())
		if seconds >= 60:
			raise ValueError("초는 0~59 사이여야 합니다.")
		return float(minutes * 60 + seconds)

	if len(parts) == 3 and all(part.strip().isdigit() for part in parts):
		hours = int(parts[0].strip())
		minutes = int(parts[1].strip())
		seconds = int(parts[2].strip())
		if minutes >= 60 or seconds >= 60:
			raise ValueError("분/초는 0~59 사이여야 합니다.")
		return float(hours * 3600 + minutes * 60 + seconds)

	space_parts = re.split(r"\s+", text)
	if len(space_parts) == 2 and all(part.isdigit() for part in space_parts):
		minutes = int(space_parts[0])
		seconds = int(space_parts[1])
		if seconds >= 60:
			raise ValueError("초는 0~59 사이여야 합니다.")
		return float(minutes * 60 + seconds)

	if len(space_parts) == 3 and all(part.isdigit() for part in space_parts):
		hours = int(space_parts[0])
		minutes = int(space_parts[1])
		seconds = int(space_parts[2])
		if minutes >= 60 or seconds >= 60:
			raise ValueError("분/초는 0~59 사이여야 합니다.")
		return float(hours * 3600 + minutes * 60 + seconds)

	# Handle mixed separators such as Korean unit labels: "70 분 00 초", "01 시간 10 분 00 초".
	digit_parts = re.findall(r"\d+", text)
	if len(digit_parts) == 2:
		minutes = int(digit_parts[0])
		seconds = int(digit_parts[1])
		if seconds >= 60:
			raise ValueError("초는 0~59 사이여야 합니다.")
		return float(minutes * 60 + seconds)

	if len(digit_parts) == 3:
		hours = int(digit_parts[0])
		minutes = int(digit_parts[1])
		seconds = int(digit_parts[2])
		if minutes >= 60 or seconds >= 60:
			raise ValueError("분/초는 0~59 사이여야 합니다.")
		return float(hours * 3600 + minutes * 60 + seconds)

	raise ValueError("지원 형식: 70, 70:00, 01:10:00, 70 00, 01 10 00, 70 분 00 초")

def split_player_label(player_label: str) -> tuple[str, str]:
	label = player_label.strip()
	if not label:
		return "", ""
	match = re.match(r"^(\d+)\.\s*(.+)$", label)
	if match:
		return match.group(1), match.group(2).strip()
	match = re.match(r"^(\d+)\s+(.+)$", label)
	if match:
		return match.group(1), match.group(2).strip()
	return "", label


def _normalize_player_name_for_match(player_label: str) -> str:
	_, name = split_player_label(player_label)
	base = name.strip().casefold() if name else player_label.strip().casefold()
	# Normalize accents/punctuation so sources with slightly different spellings still match.
	base = unicodedata.normalize("NFKD", base)
	base = "".join(ch for ch in base if not unicodedata.combining(ch))
	base = re.sub(r"[-'`´’]", " ", base)
	base = re.sub(r"[^\w\s]", " ", base)
	return re.sub(r"\s+", " ", base).strip()


def _find_player_label_index(labels: list[str], target_label: str) -> int:
	if target_label in labels:
		return labels.index(target_label)
	target_name = _normalize_player_name_for_match(target_label)
	if not target_name:
		return -1
	for index, candidate in enumerate(labels):
		if _normalize_player_name_for_match(candidate) == target_name:
			return index
	return -1


def load_players_from_file(file_path: str) -> tuple[list[str], list[str]]:
	try:
		with open(file_path, "r", encoding="utf-8") as f:
			lines = f.readlines()
		starting_players: list[str] = []
		bench_players: list[str] = []
		in_bench_section = False
		for raw_line in lines:
			line = raw_line.strip()
			if not line:
				continue
			normalized = line.replace(" ", "").upper()
			if line.startswith("#"):
				continue
			if normalized in ("[STARTING]", "[선발]", "선발"):
				in_bench_section = False
				continue
			if normalized in ("[BENCH]", "[교체]", "교체"):
				in_bench_section = True
				continue
			if in_bench_section:
				bench_players.append(line)
			else:
				starting_players.append(line)

		# 구분자가 없는 예전 형식 파일도 동작하도록 앞 11명을 선발로 취급
		if not bench_players and len(starting_players) > 11:
			bench_players = starting_players[11:]
			starting_players = starting_players[:11]

		return starting_players, bench_players
	except (FileNotFoundError, OSError):
		return [], []


def format_player_label(jersey_number: str, player_name: str) -> str:
	name = player_name.strip()
	if not jersey_number.strip():
		return name
	if not name:
		return jersey_number.strip()
	return f"{jersey_number.strip()}. {name}"


def show_error(title: str, message: str) -> None:
	root = tk.Tk()
	root.withdraw()
	try:
		messagebox.showerror(title, message, parent=root)
	finally:
		root.destroy()


def parse_fotmob_match_id(match_url: str) -> str:
	parsed = urlparse(match_url.strip())
	if not parsed.netloc or "fotmob.com" not in parsed.netloc.lower():
		raise ValueError("FotMob URL이 아닙니다.")

	fragment = parsed.fragment.strip()
	if fragment.isdigit():
		return fragment

	query_match_id = parse_qs(parsed.query).get("matchId", [""])[0].strip()
	if query_match_id.isdigit():
		return query_match_id

	fallback = re.search(r"(?:matchId=|#)(\d+)", match_url)
	if fallback:
		return fallback.group(1)

	raise ValueError("URL에서 matchId를 찾을 수 없습니다. 예: ...#4837419")


def fetch_json(url: str, timeout: float = 20.0) -> dict:
	headers = {
		"User-Agent": "Mozilla/5.0",
		"Accept": "application/json,text/plain,*/*",
		"Referer": "https://www.fotmob.com/",
	}
	request = Request(url, headers=headers)
	with urlopen(request, timeout=timeout) as response:
		payload = response.read().decode("utf-8", errors="replace")

	if payload.lstrip().startswith("<"):
		raise ValueError("JSON 대신 HTML이 내려왔습니다. (접근 제한 가능)")

	try:
		parsed = json.loads(payload)
	except json.JSONDecodeError as error:
		raise ValueError(f"JSON 파싱 실패: {error}") from error

	if not isinstance(parsed, dict):
		raise ValueError("응답 구조가 예상과 다릅니다.")
	return parsed


def fetch_text(url: str, timeout: float = 20.0) -> str:
	headers = {
		"User-Agent": "Mozilla/5.0",
		"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
		"Referer": "https://www.fotmob.com/",
	}
	request = Request(url, headers=headers)
	with urlopen(request, timeout=timeout) as response:
		return response.read().decode("utf-8", errors="replace")


def _clean_html_text(text: str) -> str:
	cleaned = unescape(text)
	cleaned = re.sub(r"<[^>]+>", "", cleaned)
	cleaned = cleaned.replace("\u200e", "").replace("\u200f", "")
	cleaned = cleaned.replace("\xa0", " ")
	cleaned = re.sub(r"\s+", " ", cleaned)
	return cleaned.strip(" .,\t\r\n")


def _dedupe_keep_order(items: list[str]) -> list[str]:
	seen: set[str] = set()
	result: list[str] = []
	for item in items:
		if not item or item in seen:
			continue
		seen.add(item)
		result.append(item)
	return result


def _extract_shirt_number_map_from_html(html: str) -> dict[str, str]:
	name_to_number: dict[str, str] = {}
	for match in re.finditer(
		r'<span[^>]*title="([^"]+)"[^>]*LineupPlayerText[^>]*>.*?<span[^>]*Shirt[^>]*>\s*(\d{1,3})\s*</span>',
		html,
		re.IGNORECASE | re.DOTALL,
	):
		name = _clean_html_text(match.group(1))
		number = match.group(2).strip()
		if not name or not number:
			continue
		name_to_number.setdefault(_normalize_player_name_for_match(name), number)

	for match in re.finditer(
		r'"name"\s*:\s*"([^\"]+)".{0,1200}?"shirtNumber"\s*:\s*"(\d{1,3})"',
		html,
		re.IGNORECASE | re.DOTALL,
	):
		name = _clean_html_text(match.group(1))
		number = match.group(2).strip()
		if not name or not number:
			continue
		name_to_number.setdefault(_normalize_player_name_for_match(name), number)
	return name_to_number


def _extract_player_id_map_from_html(html: str) -> dict[str, str]:
	name_to_id: dict[str, str] = {}
	for match in re.finditer(r'<a[^>]*href="/players/(\d+)/([^"?#]+)[^"]*"[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
		player_id = match.group(1).strip()
		player_name = _clean_html_text(match.group(3))
		slug_name = unquote(match.group(2)).replace("-", " ").strip()
		if not player_name or "css-" in player_name.lower() or len(player_name) > 60:
			player_name = slug_name
		if not player_id or not player_name:
			continue
		name_to_id.setdefault(_normalize_player_name_for_match(player_name), player_id)
		if slug_name:
			name_to_id.setdefault(_normalize_player_name_for_match(slug_name), player_id)
	return name_to_id


def _extract_players_and_ids_from_html_block(block_html: str, shirt_number_map: dict[str, str]) -> tuple[list[str], dict[str, str]]:
	players: list[str] = []
	player_id_map: dict[str, str] = {}
	for match in re.finditer(r'<a[^>]*href="/players/(\d+)/([^"?#]+)[^"]*"[^>]*>(.*?)</a>', block_html, re.IGNORECASE | re.DOTALL):
		player_id = match.group(1).strip()
		player_name = _clean_html_text(match.group(3))
		slug_name = unquote(match.group(2)).replace("-", " ").strip()
		if not player_name or "css-" in player_name.lower() or len(player_name) > 60:
			player_name = slug_name
		if not player_name:
			continue
		shirt_number = shirt_number_map.get(_normalize_player_name_for_match(player_name), "")
		label = format_player_label(shirt_number, player_name)
		if label and label not in players:
			players.append(label)
		if player_id:
			player_id_map.setdefault(label, player_id)
			normalized_name = _normalize_player_name_for_match(player_name)
			if normalized_name:
				player_id_map.setdefault(normalized_name, player_id)
			if slug_name:
				player_id_map.setdefault(_normalize_player_name_for_match(slug_name), player_id)

	if not players:
		for text_match in re.finditer(r'<span[^>]*PlayerName[^>]*>(.*?)</span>', block_html, re.IGNORECASE | re.DOTALL):
			player_name = _clean_html_text(text_match.group(1))
			if not player_name:
				continue
			shirt_number = shirt_number_map.get(_normalize_player_name_for_match(player_name), "")
			label = format_player_label(shirt_number, player_name)
			if label and label not in players:
				players.append(label)

	return players, player_id_map


def _extract_lineups_from_match_html(match_url: str, match_id: str) -> dict:
	html = fetch_text(match_url)
	shirt_number_map = _extract_shirt_number_map_from_html(html)

	lineup_para_match = re.search(r"<p[^>]*>The lineups are:(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
	if not lineup_para_match:
		raise ValueError("경기 페이지에서 선발 명단 섹션을 찾지 못했습니다.")

	lineup_para_html = lineup_para_match.group(1)
	segments = [segment for segment in lineup_para_html.split("<br/>") if segment.strip()]
	parsed_teams: list[tuple[str, list[str]]] = []
	team_id_maps: list[dict[str, str]] = []
	for segment in segments:
		segment_match = re.search(
			r"^\s*([^<]+?)\s*<!-- -->\s*<!-- -->\([^)]*\)<!-- -->:\s*(.*)$",
			segment,
			re.DOTALL,
		)
		if not segment_match:
			continue
		team_name = _clean_html_text(segment_match.group(1))
		players_html = segment_match.group(2)
		starter_names, starter_id_map = _extract_players_and_ids_from_html_block(players_html, shirt_number_map)
		starter_names = _dedupe_keep_order(starter_names)
		if team_name and starter_names:
			parsed_teams.append((team_name, starter_names))
			team_id_maps.append(starter_id_map)

	if len(parsed_teams) < 2:
		raise ValueError("경기 페이지에서 홈/어웨이 선발 명단을 찾지 못했습니다.")

	bench_blocks = re.findall(r"<ul[^>]*BenchContainer[^>]*>(.*?)</ul>", html, re.IGNORECASE | re.DOTALL)
	bench_lists: list[list[str]] = []
	bench_id_maps: list[dict[str, str]] = []
	for block in bench_blocks:
		players, bench_id_map = _extract_players_and_ids_from_html_block(block, shirt_number_map)
		players = _dedupe_keep_order(players)
		if len(players) >= 3:
			bench_lists.append(players)
			bench_id_maps.append(bench_id_map)

	home_team_name, home_starters = parsed_teams[0]
	away_team_name, away_starters = parsed_teams[1]
	home_bench = bench_lists[0] if len(bench_lists) >= 1 else []
	away_bench = bench_lists[1] if len(bench_lists) >= 2 else []
	home_player_id_map = dict(team_id_maps[0]) if len(team_id_maps) >= 1 else {}
	away_player_id_map = dict(team_id_maps[1]) if len(team_id_maps) >= 2 else {}
	if len(bench_id_maps) >= 1:
		for key, value in bench_id_maps[0].items():
			home_player_id_map.setdefault(key, value)
	if len(bench_id_maps) >= 2:
		for key, value in bench_id_maps[1].items():
			away_player_id_map.setdefault(key, value)

	return {
		"home_team_name": home_team_name,
		"away_team_name": away_team_name,
		"home_starting": home_starters,
		"home_bench": home_bench,
		"away_starting": away_starters,
		"away_bench": away_bench,
		"home_player_id_map": home_player_id_map,
		"away_player_id_map": away_player_id_map,
		"home_substitutions": [],
		"away_substitutions": [],
		"source": f"html:{match_id}",
	}


def _build_name_set_from_labels(labels: list[str]) -> set[str]:
	return {_normalize_player_name_for_match(label) for label in labels if label.strip()}


def _build_name_to_label_map(labels: list[str]) -> dict[str, str]:
	name_to_label: dict[str, str] = {}
	for label in labels:
		cleaned = str(label).strip()
		if not cleaned:
			continue
		normalized = _normalize_player_name_for_match(cleaned)
		if not normalized:
			continue
		current = name_to_label.get(normalized, "")
		current_jersey, _ = split_player_label(current)
		new_jersey, _ = split_player_label(cleaned)
		if not current or (not current_jersey and new_jersey):
			name_to_label[normalized] = cleaned
	return name_to_label


def _extract_substitutions_from_match_html(
	match_url: str,
	home_starting: list[str],
	home_bench: list[str],
	away_starting: list[str],
	away_bench: list[str],
) -> tuple[list[dict], list[dict]]:
	html = fetch_text(match_url)
	shirt_number_map = _extract_shirt_number_map_from_html(html)

	def _resolve_label(name: str, label_map: dict[str, str]) -> str:
		normalized = _normalize_player_name_for_match(name)
		if not normalized:
			return name
		label = label_map.get(normalized)
		if label:
			return label
		shirt = shirt_number_map.get(normalized, "").strip()
		if shirt:
			return format_player_label(shirt, name)
		return name

	def _append_substitution(
		target: list[dict],
		minute: int,
		out_name: str,
		in_name: str,
		label_map: dict[str, str],
		seen: set[tuple[int, str, str]],
	) -> None:
		in_norm = _normalize_player_name_for_match(in_name)
		out_norm = _normalize_player_name_for_match(out_name)
		if not in_norm or not out_norm:
			return
		display_minute = _normalize_fotmob_substitution_minute(minute)
		period_label = _fotmob_period_label_from_substitution_minute(minute)
		event_key = (display_minute, out_norm, in_norm)
		if event_key in seen:
			return
		seen.add(event_key)
		in_norm = _normalize_player_name_for_match(in_name)
		out_norm = _normalize_player_name_for_match(out_name)
		target.append(
			{
				"source_minute": minute,
				"minute": display_minute,
				"out_player": _resolve_label(out_name, label_map),
				"in_player": _resolve_label(in_name, label_map),
				"period_label": period_label,
			}
		)

	# Parse each event <div> block by explicit opening tags.
	# Using a broad "MatchEventItemWrapper..." regex can merge multiple events into one chunk,
	# which scrambles OUT/IN pairing when substitutions share the same minute.
	event_starts = list(
		re.finditer(r"<div[^>]*MatchEventItemWrapper[^>]*>", html, re.IGNORECASE)
	)
	event_blocks: list[str] = []
	for index, start_match in enumerate(event_starts):
		start = start_match.start()
		end = event_starts[index + 1].start() if index + 1 < len(event_starts) else len(html)
		event_blocks.append(html[start:end])

	home_label_map = _build_name_to_label_map(home_starting + home_bench)
	away_label_map = _build_name_to_label_map(away_starting + away_bench)
	home_pool = _build_name_set_from_labels(home_starting + home_bench)
	away_pool = _build_name_set_from_labels(away_starting + away_bench)
	home_subs: list[dict] = []
	away_subs: list[dict] = []
	html_period_lookup: list[dict] = []

	event_rows: list[tuple[str, str, str]] = []
	current_period = "전반"
	for event_block in event_blocks:
		event_type_match = re.search(r'"type"\s*:\s*"([^"]+)"', event_block, re.IGNORECASE)
		event_type = event_type_match.group(1).strip().casefold() if event_type_match else ""
		if event_type == "half":
			half_short_match = re.search(r'"halfStrShort"\s*:\s*"([^"]*)"', event_block, re.IGNORECASE)
			half_key_match = re.search(r'"halfStrKey"\s*:\s*"([^"]*)"', event_block, re.IGNORECASE)
			current_period = _next_period_from_half_event(
				{
					"halfStrShort": half_short_match.group(1) if half_short_match else "",
					"halfStrKey": half_key_match.group(1) if half_key_match else "",
				},
				current_period,
			)
			continue

		in_names_raw = re.findall(
			r"<span[^>]*class=\"[^\"]*SubIn[^\"]*\"[^>]*>(.*?)</span>",
			event_block,
			re.IGNORECASE | re.DOTALL,
		)
		out_names_raw = re.findall(
			r"<span[^>]*class=\"[^\"]*SubOut[^\"]*\"[^>]*>(.*?)</span>",
			event_block,
			re.IGNORECASE | re.DOTALL,
		)
		in_names = [_clean_html_text(text) for text in in_names_raw if _clean_html_text(text)]
		out_names = [_clean_html_text(text) for text in out_names_raw if _clean_html_text(text)]
		if not in_names or not out_names:
			continue

		minute_text = ""
		for candidate in re.findall(r"(?:EventTimeMain|SubText)[^>]*>([^<]+)</span>", event_block, re.IGNORECASE):
			if _parse_fotmob_minute_text(candidate) is not None:
				minute_text = candidate
				break
		if not minute_text:
			continue

		is_home_match = re.search(r'"isHome"\s*:\s*(true|false)', event_block, re.IGNORECASE)
		is_home = None
		if is_home_match:
			is_home = is_home_match.group(1).strip().lower() == "true"

		pair_count = min(len(in_names), len(out_names))
		for index in range(pair_count):
			event_rows.append((minute_text, in_names[index], out_names[index]))
			minute = _parse_fotmob_minute_text(minute_text)
			if minute is not None:
				html_period_lookup.append(
					{
						"minute": minute,
						"is_home": is_home,
						"out_norm": _normalize_player_name_for_match(out_names[index]),
						"in_norm": _normalize_player_name_for_match(in_names[index]),
						"period_label": current_period,
					}
				)

	seen_events: set[tuple[int, str, str]] = set()
	for minute_text, in_name_raw, out_name_raw in event_rows:
		minute = _parse_fotmob_minute_text(minute_text)
		if minute is None:
			continue
		in_name = _clean_html_text(in_name_raw)
		out_name = _clean_html_text(out_name_raw)
		if not in_name or not out_name:
			continue
		in_norm = _normalize_player_name_for_match(in_name)
		out_norm = _normalize_player_name_for_match(out_name)

		if out_norm in home_pool or in_norm in home_pool:
			_append_substitution(home_subs, minute, out_name, in_name, home_label_map, seen_events)
		elif out_norm in away_pool or in_norm in away_pool:
			_append_substitution(away_subs, minute, out_name, in_name, away_label_map, seen_events)

	# Fallback/correction: some pages are one-sided in DOM or side-classification gets skewed.
	# Use embedded JSON timeline events (with explicit isHome) to restore missing side substitutions.
	json_home_subs: list[dict] = []
	json_away_subs: list[dict] = []
	json_seen: set[tuple[int, str, str]] = set()
	json_pattern = re.compile(
		r'"type"\s*:\s*"Substitution".*?"time"\s*:\s*(\d+).*?"isHome"\s*:\s*(true|false).*?"swap"\s*:\s*\[\s*\{"name"\s*:\s*"([^"]+)"[^\]]*?\}\s*,\s*\{"name"\s*:\s*"([^"]+)"',
		re.IGNORECASE | re.DOTALL,
	)
	for match in json_pattern.finditer(html):
		minute = _to_int_minutes(match.group(1))
		if minute is None:
			continue
		is_home = match.group(2).strip().lower() == "true"
		in_name = unescape(match.group(3)).strip()
		out_name = unescape(match.group(4)).strip()
		if not in_name or not out_name:
			continue
		if is_home:
			_append_substitution(json_home_subs, minute, out_name, in_name, home_label_map, json_seen)
		else:
			_append_substitution(json_away_subs, minute, out_name, in_name, away_label_map, json_seen)

	if (not home_subs and json_home_subs) or (not away_subs and json_away_subs):
		# Keep DOM result when present, but fill missing side from explicit isHome timeline data.
		home_subs = _merge_substitution_lists(home_subs, json_home_subs)
		away_subs = _merge_substitution_lists(away_subs, json_away_subs)

		# If DOM parsing collapsed both teams into one side, prune moved events from the other side.
		if not away_subs and json_away_subs:
			away_subs = json_away_subs
		if not home_subs and json_home_subs:
			home_subs = json_home_subs

		json_home_keys = {
			(item.get("minute"), _normalize_player_name_for_match(str(item.get("out_player", ""))), _normalize_player_name_for_match(str(item.get("in_player", ""))))
			for item in json_home_subs
		}
		json_away_keys = {
			(item.get("minute"), _normalize_player_name_for_match(str(item.get("out_player", ""))), _normalize_player_name_for_match(str(item.get("in_player", ""))))
			for item in json_away_subs
		}
		home_subs = [
			item
			for item in home_subs
			if (
				item.get("minute"),
				_normalize_player_name_for_match(str(item.get("out_player", ""))),
				_normalize_player_name_for_match(str(item.get("in_player", ""))),
			)
			not in json_away_keys
		]
		away_subs = [
			item
			for item in away_subs
			if (
				item.get("minute"),
				_normalize_player_name_for_match(str(item.get("out_player", ""))),
				_normalize_player_name_for_match(str(item.get("in_player", ""))),
			)
			not in json_home_keys
		]

	_apply_substitution_period_lookup(home_subs, html_period_lookup, is_home=True)
	_apply_substitution_period_lookup(away_subs, html_period_lookup, is_home=False)

	home_subs.sort(key=lambda item: (int(item.get("minute", 0)), str(item.get("out_player", ""))))
	away_subs.sort(key=lambda item: (int(item.get("minute", 0)), str(item.get("out_player", ""))))

	return home_subs, away_subs


def _parse_fotmob_minute_text(value) -> int | None:
	if value is None:
		return None
	text = str(value)
	if not text.strip():
		return None

	# Remove apostrophes and bidirectional marks often included in minute text like "64‎’‎".
	cleaned = text.replace("\u200e", "").replace("\u200f", "")
	cleaned = re.sub(r"[^0-9+]", "", cleaned)
	if not cleaned:
		return None

	if "+" in cleaned:
		parts = [part for part in cleaned.split("+") if part]
		if not parts:
			return None
		minute = 0
		for part in parts:
			if not part.isdigit():
				return None
			minute += int(part)
	else:
		if not cleaned.isdigit():
			return None
		minute = int(cleaned)

	if minute < 0 or minute > 150:
		return None
	return minute


def _normalize_fotmob_substitution_minute(minute: int) -> int:
	return {
		46: 45,
		91: 90,
		106: 105,
		121: 120,
	}.get(minute, minute)


def _fotmob_period_label_from_substitution_minute(minute: int) -> str:
	if minute <= 45:
		return "전반"
	if minute <= 90:
		return "후반"
	if minute <= 105:
		return "연장전반"
	return "연장후반"


def _normalize_fotmob_period_label(value) -> str:
	if value is None:
		return ""
	if isinstance(value, dict):
		for key in ("short", "shortKey", "key", "name", "value", "period", "type"):
			if key not in value:
				continue
			parsed = _normalize_fotmob_period_label(value.get(key))
			if parsed:
				return parsed
		return ""

	raw = str(value).strip()
	if not raw:
		return ""
	normalized = re.sub(r"[^a-z0-9]+", "", raw.casefold())

	if normalized in ("1", "firsthalf", "h1", "period1"):
		return "전반"
	if normalized in ("2", "secondhalf", "h2", "period2"):
		return "후반"
	if normalized in (
		"3",
		"firstextrahalf",
		"extrafirsthalf",
		"extrahalf1",
		"extraperiod1",
		"period3",
		"extratimefirsthalf",
	):
		return "연장전반"
	if normalized in (
		"4",
		"secondextrahalf",
		"extrasecondhalf",
		"extrahalf2",
		"extraperiod2",
		"period4",
		"extratimesecondhalf",
	):
		return "연장후반"
	return ""


def _extract_fotmob_period_label_from_event(event: dict) -> str:
	for key in ("period", "periodType", "periodName", "half", "gamePeriod"):
		if key not in event:
			continue
		parsed = _normalize_fotmob_period_label(event.get(key))
		if parsed:
			return parsed

	shotmap_event = event.get("shotmapEvent")
	if isinstance(shotmap_event, dict):
		parsed = _normalize_fotmob_period_label(shotmap_event.get("period"))
		if parsed:
			return parsed

	return ""


def _next_period_from_half_event(event: dict, current_period: str) -> str:
	half_short = str(event.get("halfStrShort", "") or "").strip().upper()
	half_key = str(event.get("halfStrKey", "") or "").strip().casefold()

	if half_short == "HT" or "halftime" in half_key:
		return "후반"
	if "first" in half_key and "extra" in half_key:
		return "연장전반"
	if "second" in half_key and "extra" in half_key:
		return "연장후반"
	return current_period


def _collect_timeline_event_lists(data, output: list[list[dict]]) -> None:
	if isinstance(data, list):
		dict_items = [item for item in data if isinstance(item, dict)]
		if dict_items and all("type" in item for item in dict_items):
			if any("time" in item or "timeStr" in item for item in dict_items):
				output.append(dict_items)
		for item in data:
			_collect_timeline_event_lists(item, output)
		return

	if isinstance(data, dict):
		for value in data.values():
			_collect_timeline_event_lists(value, output)


def _build_substitution_period_lookup(data: dict) -> list[dict]:
	event_lists: list[list[dict]] = []
	_collect_timeline_event_lists(data, event_lists)
	lookup: list[dict] = []
	seen: set[tuple[int, bool | None, str, str, str]] = set()

	for events in event_lists:
		current_period = "전반"
		for event in events:
			event_type = str(event.get("type", "") or "").strip().casefold()
			explicit_period = _extract_fotmob_period_label_from_event(event)
			event_period = explicit_period or current_period

			if event_type == "half":
				current_period = _next_period_from_half_event(event, current_period)
				continue

			if "substitution" not in event_type:
				if explicit_period:
					current_period = explicit_period
				continue

			minute = _to_int_minutes(event.get("time"))
			if minute is None:
				minute = _to_int_minutes(event.get("timeStr"))
			if minute is None:
				continue

			is_home = event.get("isHome") if isinstance(event.get("isHome"), bool) else None
			swap = event.get("swap")
			in_norm = ""
			out_norm = ""
			if isinstance(swap, list) and len(swap) >= 2:
				in_name = str((swap[0] or {}).get("name", "") or "").strip() if isinstance(swap[0], dict) else ""
				out_name = str((swap[1] or {}).get("name", "") or "").strip() if isinstance(swap[1], dict) else ""
				in_norm = _normalize_player_name_for_match(in_name)
				out_norm = _normalize_player_name_for_match(out_name)

			if not event_period:
				continue
			event_key = (minute, is_home, out_norm, in_norm, event_period)
			if event_key in seen:
				continue
			seen.add(event_key)
			lookup.append(
				{
					"minute": minute,
					"is_home": is_home,
					"out_norm": out_norm,
					"in_norm": in_norm,
					"period_label": event_period,
				}
			)

	return lookup


def _apply_substitution_period_lookup(substitutions: list[dict], period_lookup: list[dict], is_home: bool) -> None:
	if not substitutions or not period_lookup:
		return

	for substitution in substitutions:
		current_label = _normalize_fotmob_period_label(substitution.get("period_label"))
		if current_label:
			substitution["period_label"] = current_label
			continue

		minute = _to_int_minutes(substitution.get("minute"))
		if minute is None:
			continue
		out_norm = _normalize_player_name_for_match(str(substitution.get("out_player", "")))
		in_norm = _normalize_player_name_for_match(str(substitution.get("in_player", "")))

		exact_matches = [
			item
			for item in period_lookup
			if item.get("minute") == minute
			and (item.get("is_home") is None or item.get("is_home") is is_home)
			and item.get("out_norm") == out_norm
			and item.get("in_norm") == in_norm
			and item.get("period_label")
		]
		if exact_matches:
			substitution["period_label"] = str(exact_matches[0].get("period_label", ""))
			continue

		side_matches = [
			item
			for item in period_lookup
			if item.get("minute") == minute
			and (item.get("is_home") is None or item.get("is_home") is is_home)
			and item.get("period_label")
		]
		labels = {str(item.get("period_label", "")) for item in side_matches if item.get("period_label")}
		if len(labels) == 1:
			substitution["period_label"] = next(iter(labels))


def _merge_substitution_lists(primary: list[dict], secondary: list[dict]) -> list[dict]:
	merged_by_key: dict[tuple[int, str, str], dict] = {}
	for source in (primary, secondary):
		for item in source:
			if not isinstance(item, dict):
				continue
			minute = _to_int_minutes(item.get("minute"))
			out_player = str(item.get("out_player", "")).strip()
			in_player = str(item.get("in_player", "")).strip()
			if minute is None or not out_player or not in_player:
				continue

			normalized_item = {
				"minute": minute,
				"out_player": out_player,
				"in_player": in_player,
				"period_label": _normalize_fotmob_period_label(item.get("period_label")),
				"fotmob_team_id": str(item.get("fotmob_team_id", "") or "").strip(),
				"fotmob_player_id": str(item.get("fotmob_player_id", "") or "").strip(),
				"fotmob_sub_out_player_id": str(item.get("fotmob_sub_out_player_id", "") or "").strip(),
				"fotmob_sub_in_player_id": str(item.get("fotmob_sub_in_player_id", "") or "").strip(),
			}

			def _id_score(record: dict) -> int:
				return sum(
					bool(record.get(field))
					for field in ("fotmob_team_id", "fotmob_player_id", "fotmob_sub_out_player_id", "fotmob_sub_in_player_id")
				)

			key = (
				minute,
				_normalize_player_name_for_match(out_player),
				_normalize_player_name_for_match(in_player),
			)
			existing = merged_by_key.get(key)
			if existing is None:
				merged_by_key[key] = normalized_item
				continue

			existing_score = _id_score(existing)
			new_score = _id_score(normalized_item)

			# API records carry FotMob IDs while HTML fallback records usually don't.
			# Keep the richer (API) record as source of truth for jersey mapping.
			if new_score > existing_score:
				merged_by_key[key] = normalized_item
				continue

			if new_score < existing_score:
				continue

			for field in ("fotmob_team_id", "fotmob_player_id", "fotmob_sub_out_player_id", "fotmob_sub_in_player_id"):
				if not existing.get(field):
					existing[field] = normalized_item.get(field, "")
			if not existing.get("period_label") and normalized_item.get("period_label"):
				existing["period_label"] = normalized_item.get("period_label", "")

			existing_out_jersey, _ = split_player_label(str(existing.get("out_player", "")))
			existing_in_jersey, _ = split_player_label(str(existing.get("in_player", "")))
			new_out_jersey, _ = split_player_label(out_player)
			new_in_jersey, _ = split_player_label(in_player)
			if not existing_out_jersey and new_out_jersey:
				existing["out_player"] = out_player
			if not existing_in_jersey and new_in_jersey:
				existing["in_player"] = in_player

	merged = list(merged_by_key.values())
	merged.sort(key=lambda item: (int(item.get("minute", 0)), str(item.get("out_player", ""))))
	return merged


def _deep_find_dict_by_key(data, keys: tuple[str, ...]) -> dict | None:
	if isinstance(data, dict):
		for key in keys:
			value = data.get(key)
			if isinstance(value, dict):
				return value
		for value in data.values():
			found = _deep_find_dict_by_key(value, keys)
			if found is not None:
				return found
	elif isinstance(data, list):
		for item in data:
			found = _deep_find_dict_by_key(item, keys)
			if found is not None:
				return found
	return None


def _collect_lineup_candidates(data, output: list[dict]) -> None:
	if isinstance(data, dict):
		keyset = {str(key).lower() for key in data.keys()}
		if any(key in keyset for key in ("starters", "startinglineup", "bench", "substitutes", "subs")):
			output.append(data)
		for value in data.values():
			_collect_lineup_candidates(value, output)
	elif isinstance(data, list):
		for item in data:
			_collect_lineup_candidates(item, output)


def _pick_name(player: dict) -> str:
	if isinstance(player.get("player"), dict):
		player = player.get("player")
	elif isinstance(player.get("athlete"), dict):
		player = player.get("athlete")
	elif isinstance(player.get("participant"), dict):
		player = player.get("participant")
	for key in ("name", "fullName", "full_name", "playerName", "usualName", "shortName"):
		value = player.get(key)
		if isinstance(value, str) and value.strip():
			return unescape(value.strip())
	first_name = player.get("firstName")
	last_name = player.get("lastName")
	if isinstance(first_name, str) and isinstance(last_name, str):
		combined = f"{first_name} {last_name}".strip()
		if combined:
			return unescape(combined)
	return ""


def _pick_number(player: dict) -> str:
	if isinstance(player.get("player"), dict):
		player = player.get("player")
	elif isinstance(player.get("athlete"), dict):
		player = player.get("athlete")
	elif isinstance(player.get("participant"), dict):
		player = player.get("participant")
	for key in ("shirtNo", "shirtNumber", "jerseyNumber", "jerseyNo", "shirt"):
		value = player.get(key)
		if isinstance(value, int):
			return str(value)
		if isinstance(value, str) and value.strip().isdigit():
			return value.strip()

	# Some payloads use a generic "number" for non-jersey semantics.
	# Only use it as a last-resort fallback.
	number_value = player.get("number")
	if isinstance(number_value, int):
		return str(number_value)
	if isinstance(number_value, str) and number_value.strip().isdigit():
		return number_value.strip()
	return ""


def _pick_player_id(player: dict) -> str:
	if isinstance(player.get("player"), dict):
		player = player.get("player")
	elif isinstance(player.get("athlete"), dict):
		player = player.get("athlete")
	elif isinstance(player.get("participant"), dict):
		player = player.get("participant")
	for key in ("id", "playerId", "player_id", "fotmobPlayerId", "fotmob_player_id"):
		value = player.get(key)
		if isinstance(value, int):
			return str(value)
		if isinstance(value, str) and value.strip():
			return value.strip()
	return ""


def _normalize_player_label(player) -> str:
	if isinstance(player, str):
		return unescape(player.strip())
	if not isinstance(player, dict):
		return ""
	name = _pick_name(player)
	number = _pick_number(player)
	if not name:
		return ""
	return format_player_label(number, name)


def _extract_players_from_list(items: list) -> list[str]:
	players: list[str] = []
	for item in items:
		label = _normalize_player_label(item)
		if label and label not in players:
			players.append(label)
	return players


def _extract_players_and_ids_from_list(items: list) -> tuple[list[str], dict[str, str]]:
	players: list[str] = []
	player_ids: dict[str, str] = {}
	for item in items:
		if not isinstance(item, dict):
			label = _normalize_player_label(item)
			if label and label not in players:
				players.append(label)
			continue

		label = _normalize_player_label(item)
		if label and label not in players:
			players.append(label)

		player_id_text = _pick_player_id(item)
		if not label or not player_id_text:
			continue
		player_ids.setdefault(label, player_id_text)
		normalized_name = _normalize_player_name_for_match(label)
		if normalized_name:
			player_ids.setdefault(normalized_name, player_id_text)

	return players, player_ids


def _extract_team_lineup(team_data: dict) -> tuple[list[str], list[str], dict[str, str]]:
	starters_keys = ("starters", "startingLineup", "startingXI")
	bench_keys = ("bench", "substitutes", "subs", "benchPlayers")

	starters_raw = None
	bench_raw = None
	for key in starters_keys:
		value = team_data.get(key)
		if isinstance(value, list):
			starters_raw = value
			break
	for key in bench_keys:
		value = team_data.get(key)
		if isinstance(value, list):
			bench_raw = value
			break

	if starters_raw is None and isinstance(team_data.get("players"), list):
		starters_guess: list = []
		bench_guess: list = []
		for player in team_data.get("players", []):
			if not isinstance(player, dict):
				continue
			is_starter = bool(player.get("isStarter") or player.get("starter"))
			if not is_starter:
				role = str(player.get("lineupType", "")).lower()
				status = str(player.get("status", "")).lower()
				is_starter = role in ("starter", "starting") or status in ("starter", "starting")
			if is_starter:
				starters_guess.append(player)
			else:
				bench_guess.append(player)
		starters_raw = starters_guess
		bench_raw = bench_guess

	starters, starter_id_map = _extract_players_and_ids_from_list(starters_raw or [])
	bench, bench_id_map = _extract_players_and_ids_from_list(bench_raw or [])
	player_id_map = dict(starter_id_map)
	for key, value in bench_id_map.items():
		player_id_map.setdefault(key, value)

	if not starters and isinstance(team_data.get("lineup"), list):
		starters, lineup_id_map = _extract_players_and_ids_from_list(team_data.get("lineup", []))
		for key, value in lineup_id_map.items():
			player_id_map.setdefault(key, value)

	return starters, bench, player_id_map


def _resolve_player_id_from_map(player_label: str, player_id_map: dict[str, str]) -> str:
	label = player_label.strip()
	if not label or not player_id_map:
		return ""
	jersey_no, _ = split_player_label(label)
	target_norm = _normalize_player_name_for_match(label)
	for key in (label, _normalize_player_name_for_match(label)):
		if key and key in player_id_map:
			return player_id_map[key]

	# Fallback for minor spelling mismatches (e.g. Lamara/Lamare):
	# prefer same jersey + same surname, else unique same-surname candidate.
	tokens = target_norm.split() if target_norm else []
	if not tokens:
		return ""
	target_surname = tokens[-1]
	candidates: list[tuple[str, str]] = []
	for key, value in player_id_map.items():
		key_norm = _normalize_player_name_for_match(key)
		if not key_norm:
			continue
		key_tokens = key_norm.split()
		if not key_tokens or key_tokens[-1] != target_surname:
			continue
		candidates.append((key, value))

	if not candidates:
		return ""

	if jersey_no:
		for key, value in candidates:
			cand_jersey, _ = split_player_label(key)
			if cand_jersey == jersey_no:
				return value

	unique_ids = {value for _, value in candidates if value}
	if len(unique_ids) == 1:
		return next(iter(unique_ids))
	return ""


def _extract_player_objects_from_team_data(team_data: dict) -> list[dict]:
	players: list[dict] = []
	seen_keys: set[str] = set()

	for key in (
		"starters",
		"startingLineup",
		"startingXI",
		"bench",
		"substitutes",
		"subs",
		"benchPlayers",
		"players",
		"lineup",
	):
		value = team_data.get(key)
		if not isinstance(value, list):
			continue
		for item in value:
			if not isinstance(item, dict):
				continue
			player_id = _pick_player_id(item)
			if player_id:
				unique_key = f"id:{player_id}"
			else:
				unique_key = f"label:{_normalize_player_label(item)}"
			if not unique_key or unique_key in seen_keys:
				continue
			seen_keys.add(unique_key)
			players.append(item)

	return players


def _to_int_minutes(value) -> int | None:
	minute: int | None = None
	if isinstance(value, int):
		minute = value
	elif isinstance(value, float):
		minute = int(value)
	elif isinstance(value, str):
		text = value.strip()
		if not text:
			return None
		# Handle common clock-like text from APIs: "54:00" or "01:24:30".
		clock_match = re.fullmatch(r"(\d+)\s*:\s*(\d{1,2})(?:\s*:\s*(\d{1,2}))?", text)
		if clock_match:
			first = int(clock_match.group(1))
			second = int(clock_match.group(2))
			third_raw = clock_match.group(3)
			if third_raw is None:
				if second >= 60:
					return None
				minute = first
			else:
				third = int(third_raw)
				if second >= 60 or third >= 60:
					return None
				total_seconds = first * 3600 + second * 60 + third
				minute = total_seconds // 60
		else:
			parsed = _parse_fotmob_minute_text(text)
			if parsed is not None:
				minute = parsed
			elif text.isdigit():
				minute = int(text)

	if minute is None or minute < 0:
		return None
	if minute <= 150:
		return minute
	# Some payloads provide elapsed seconds instead of minute values.
	if minute <= (150 * 60 + 59):
		return minute // 60
	return None


def _extract_substitutions_from_team_data(team_data: dict) -> list[dict]:
	players = _extract_player_objects_from_team_data(team_data)
	player_id_by_label: dict[str, str] = {}
	sub_in_by_minute: dict[int, list[tuple[str, str]]] = {}
	sub_out_by_minute: dict[int, list[tuple[str, str]]] = {}

	for player in players:
		label = _normalize_player_label(player)
		if not label:
			continue
		player_id = _pick_player_id(player)
		if player_id:
			player_id_by_label.setdefault(label, player_id)
			normalized_label = _normalize_player_name_for_match(label)
			if normalized_label:
				player_id_by_label.setdefault(normalized_label, player_id)
		performance = player.get("performance")
		if not isinstance(performance, dict):
			continue
		events = performance.get("substitutionEvents")
		if not isinstance(events, list):
			continue

		for event in events:
			if not isinstance(event, dict):
				continue
			minute = _to_int_minutes(event.get("time"))
			if minute is None or minute < 0:
				continue
			display_minute = _normalize_fotmob_substitution_minute(minute)
			event_type = str(event.get("type", "")).strip().lower()
			period_label = _extract_fotmob_period_label_from_event(event) or _fotmob_period_label_from_substitution_minute(minute)
			if "subin" in event_type:
				sub_in_by_minute.setdefault(display_minute, []).append((label, period_label))
			elif "subout" in event_type:
				sub_out_by_minute.setdefault(display_minute, []).append((label, period_label))

	substitutions: list[dict] = []
	all_minutes = sorted(set(sub_in_by_minute.keys()) | set(sub_out_by_minute.keys()))
	for minute in all_minutes:
		in_list = sub_in_by_minute.get(minute, [])
		out_list = sub_out_by_minute.get(minute, [])
		pair_count = min(len(in_list), len(out_list))
		for index in range(pair_count):
			out_player, out_period_label = out_list[index]
			in_player, in_period_label = in_list[index]
			substitutions.append(
				{
					"minute": minute,
					"display_minute": _normalize_fotmob_substitution_minute(minute),
					"out_player": out_player,
					"in_player": in_player,
					"period_label": in_period_label or out_period_label or _fotmob_period_label_from_substitution_minute(minute),
					"fotmob_sub_out_player_id": player_id_by_label.get(out_player, player_id_by_label.get(_normalize_player_name_for_match(out_player), "")),
					"fotmob_sub_in_player_id": player_id_by_label.get(in_player, player_id_by_label.get(_normalize_player_name_for_match(in_player), "")),
				}
			)

	return substitutions


def _extract_team_name(data: dict, side: str, fallback: str) -> str:
	general = data.get("general") if isinstance(data.get("general"), dict) else {}
	team_key = "homeTeam" if side == "home" else "awayTeam"
	team_info = general.get(team_key)
	if isinstance(team_info, dict):
		name = team_info.get("name")
		if isinstance(name, str) and name.strip():
			return unescape(name.strip())
	return fallback


def fetch_fotmob_lineups(match_id: str, match_url: str = "") -> dict:
	api_urls = [
		f"https://www.fotmob.com/api/matchDetails?matchId={match_id}",
		f"https://www.fotmob.com/api/matchDetails?matchId={match_id}&tab=lineup",
		f"https://www.fotmob.com/api/matchDetails?matchId={match_id}&ccode3=KOR",
		f"https://www.fotmob.com/api/matchDetails?matchId={match_id}&ccode3=USA",
	]

	last_error = ""
	data: dict | None = None
	for api_url in api_urls:
		try:
			data = fetch_json(api_url)
			break
		except Exception as error:  # pragma: no cover - network dependent
			last_error = str(error)

	if data is None:
		fallback_url = match_url.strip() or f"https://www.fotmob.com/match/{match_id}"
		lineups = _extract_lineups_from_match_html(fallback_url, match_id)
		try:
			home_subs, away_subs = _extract_substitutions_from_match_html(
				fallback_url,
				lineups.get("home_starting", []),
				lineups.get("home_bench", []),
				lineups.get("away_starting", []),
				lineups.get("away_bench", []),
			)
			lineups["home_substitutions"] = home_subs
			lineups["away_substitutions"] = away_subs
		except Exception:
			pass
		lineups["home_player_id_map"] = {}
		lineups["away_player_id_map"] = {}
		return lineups

	lineup_root = _deep_find_dict_by_key(data, ("lineup", "lineups"))
	home_team_data = None
	away_team_data = None

	if isinstance(lineup_root, dict):
		for key in ("homeTeam", "home", "team1"):
			value = lineup_root.get(key)
			if isinstance(value, dict):
				home_team_data = value
				break
		for key in ("awayTeam", "away", "team2"):
			value = lineup_root.get(key)
			if isinstance(value, dict):
				away_team_data = value
				break

	if home_team_data is None or away_team_data is None:
		candidates: list[dict] = []
		_collect_lineup_candidates(data, candidates)
		if len(candidates) >= 2:
			home_team_data = candidates[0]
			away_team_data = candidates[1]

	if home_team_data is None or away_team_data is None:
		raise ValueError("라인업 구조를 찾지 못했습니다.")

	home_starters, home_bench, home_player_id_map = _extract_team_lineup(home_team_data)
	away_starters, away_bench, away_player_id_map = _extract_team_lineup(away_team_data)

	if not home_starters or not away_starters:
		fallback_url = match_url.strip() or f"https://www.fotmob.com/match/{match_id}"
		return _extract_lineups_from_match_html(fallback_url, match_id)

	home_substitutions = _extract_substitutions_from_team_data(home_team_data)
	away_substitutions = _extract_substitutions_from_team_data(away_team_data)
	period_lookup = _build_substitution_period_lookup(data)
	_apply_substitution_period_lookup(home_substitutions, period_lookup, is_home=True)
	_apply_substitution_period_lookup(away_substitutions, period_lookup, is_home=False)
	html_lineups: dict | None = None
	if match_url.strip():
		try:
			html_lineups = _extract_lineups_from_match_html(match_url.strip(), match_id)
			html_home_substitutions, html_away_substitutions = _extract_substitutions_from_match_html(
				match_url.strip(),
				home_starters,
				home_bench,
				away_starters,
				away_bench,
			)
			_apply_substitution_period_lookup(html_home_substitutions, period_lookup, is_home=True)
			_apply_substitution_period_lookup(html_away_substitutions, period_lookup, is_home=False)
			# Keep HTML pairing quality while retaining richer API metadata (IDs/period labels) on merge.
			if html_home_substitutions or html_away_substitutions:
				home_substitutions = _merge_substitution_lists(html_home_substitutions, home_substitutions)
				away_substitutions = _merge_substitution_lists(html_away_substitutions, away_substitutions)
			else:
				home_substitutions = _merge_substitution_lists(home_substitutions, html_home_substitutions)
				away_substitutions = _merge_substitution_lists(away_substitutions, html_away_substitutions)
		except Exception:
			pass

	if html_lineups is not None:
		for key, value in html_lineups.get("home_player_id_map", {}).items():
			home_player_id_map.setdefault(key, value)
		for key, value in html_lineups.get("away_player_id_map", {}).items():
			away_player_id_map.setdefault(key, value)

	return {
		"home_team_name": _extract_team_name(data, "home", "홈팀"),
		"away_team_name": _extract_team_name(data, "away", "어웨이팀"),
		"home_starting": home_starters,
		"home_bench": home_bench,
		"away_starting": away_starters,
		"away_bench": away_bench,
		"home_player_id_map": home_player_id_map,
		"away_player_id_map": away_player_id_map,
		"home_substitutions": home_substitutions,
		"away_substitutions": away_substitutions,
		"source": "api",
	}


def save_lineup_file(file_path: Path, starting: list[str], bench: list[str]) -> None:
	lines = ["[STARTING]"]
	lines.extend(starting)
	lines.append("")
	lines.append("[BENCH]")
	lines.extend(bench)
	file_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


class VideoPlayerApp(tk.Tk):
	def _save_screenshot(self) -> str:
		"""현재 프레임을 영상 파일과 같은 폴더에 자동 저장하고 경로 또는 오류 메시지 반환."""
		if self.video_capture is None or self.video_path is None:
			messagebox.showwarning("스크린샷", "불러온 영상이 없습니다.", parent=self)
			return "저장 실패"
		# 현재 프레임 위치에서 프레임 읽기
		pos = self.current_time_seconds
		self.video_capture.set(cv2.CAP_PROP_POS_MSEC, pos * 1000)
		success, frame = self.video_capture.read()
		if not success or frame is None:
			messagebox.showerror("스크린샷", "프레임을 읽을 수 없습니다.", parent=self)
			return "저장 실패"
		# 영상 파일과 같은 폴더에 자동 저장 (중복 방지)
		folder = self.video_path.parent
		base = self.video_path.stem
		idx = int(pos)
		for n in range(1000):
			filename = f"{base}_screenshot_{idx:05d}"
			if n > 0:
				filename += f"_{n}"
			filename += ".png"
			target_path = folder / filename
			if not target_path.exists():
				break
		else:
			messagebox.showerror("스크린샷", "파일 이름이 너무 많습니다.", parent=self)
			return "저장 실패"
		try:
			frame_rgb = frame[:, :, ::-1]  # BGR→RGB view (no extra allocation)
			image = Image.fromarray(frame_rgb)
			image.save(target_path, format="PNG")
		except Exception as e:
			messagebox.showerror("스크린샷", f"저장 실패: {e}", parent=self)
			return "저장 실패"
		self.status_var.set(f"스크린샷 저장: {target_path}")
		return str(target_path)
	def _create_clip(self) -> str:
		"""현재 시점 기준 앞뒤 5초(총 10초)를 자르는 FFmpeg 초고속 재인코딩 로직"""
		if self.video_capture is None or self.video_path is None:
			messagebox.showwarning("클립 생성", "불러온 영상이 없습니다.", parent=self)
			return "저장 실패"

		current_pos = self.current_time_seconds
		# 시작 시간이 0초보다 작아지지 않도록 처리
		start_time = max(0.0, current_pos - 5.0)
		duration = 10.0

		folder = self.video_path.parent
		base = self.video_path.stem
		idx = int(current_pos)
		
		# 저장 파일 이름 겹치지 않게 인덱싱
		for n in range(1000):
			filename = f"{base}_clip_{idx:05d}"
			if n > 0:
				filename += f"_{n}"
			filename += ".mp4"
			target_path = folder / filename
			if not target_path.exists():
				break
		else:
			messagebox.showerror("클립 생성", "파일 이름이 너무 많습니다.", parent=self)
			return "저장 실패"

		# FFmpeg 명령어 (초고속 재인코딩 방식)
		command = [
			"ffmpeg",
			"-y",
			"-ss", f"{start_time:.3f}",
			"-t", f"{duration:.3f}",
			"-i", str(self.video_path),
			"-c:v", "libx264",        # 비디오를 h264 규격으로 재인코딩 (깨짐 방지)
			"-preset", "ultrafast",   # 인코딩 속도를 '가장 빠르게' 설정 (매우 중요)
			"-c:a", "aac",            # 오디오 싱크를 맞추기 위해 오디오도 재압축
			str(target_path)
		]

		try:
			# Windows의 경우 FFmpeg 실행 시 검은 콘솔창이 뜨는 것을 방지
			startupinfo = None
			if sys.platform.startswith("win"):
				startupinfo = subprocess.STARTUPINFO()
				startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

			# UI에 상태 업데이트 후 FFmpeg 실행
			self.status_var.set(f"클립 생성 중: {filename}...")
			self.update()

			# 👇 이 부분이 지워져서 저장이 안 됐던 것입니다! (실제 실행 코드)
			subprocess.run(command, check=True, startupinfo=startupinfo, capture_output=True)
			
			return f"클립 저장됨: {filename}"
			
		except FileNotFoundError:
			messagebox.showerror("클립 생성 오류", "FFmpeg가 설치되어 있지 않거나 환경 변수(PATH)에 등록되지 않았습니다.", parent=self)
			return "FFmpeg 없음"
		except subprocess.CalledProcessError as e:
			err_msg = e.stderr.decode("utf-8", errors="replace")
			messagebox.showerror("클립 생성 오류", f"FFmpeg 작업 실패:\n{err_msg}", parent=self)
			return "저장 실패"
		except Exception as e:
			messagebox.showerror("클립 생성 오류", f"알 수 없는 오류:\n{e}", parent=self)
			return "저장 실패"
	def __init__(self) -> None:
		super().__init__()
		self.title("Video Player")
		self._apply_window_icon()
		self.configure(bg=WINDOW_BG)
		self.geometry("1100x760")
		self.minsize(820, 560)

		self.video_capture = None
		self.audio_player = None
		self.video_path: Path | None = None
		self.video_fps = 30.0
		self.project_file_path: Path | None = None
		self.last_saved_project_payload: str | None = None
		self._action_key_last_press: dict[str, float] = {}
		self.video_frame_count = 0
		self.duration_seconds = 0.0
		self.current_frame_index = 0
		self.current_time_seconds = 0.0
		self.current_frame_photo = None
		self.is_playing = False
		self.is_scrubbing = False
		self.scrub_was_playing = False
		self.is_timeline_dragging = False
		self.timeline_drag_was_playing = False
		self.playback_frame_accumulator = 0.0
		self.last_tick_time = time.perf_counter()
		self._updating_seek = False
		self.timeline_start_offset_seconds = 0.0
		self.timeline_adjust_mode = False
		self.timeline_canvas_ranges: dict[tk.Canvas, tuple[float, float, str]] = {}
		self.first_half_start_seconds: float | None = None
		self.first_half_end_seconds: float | None = None
		self.second_half_start_seconds: float | None = None
		self.second_half_end_seconds: float | None = None
		self.timeline_records: list[TimelineRecord] = []
		self.record_counter = 0
		self.selected_team = "홈"
		self.selected_player: str | None = None
		self.selected_action: str | None = None
		self.team_buttons: dict[str, tk.Button] = {}
		self.player_buttons: dict[str, tk.Button] = {}
		self.action_buttons: dict[str, tk.Button] = {}
		self.result_buttons: dict[str, tk.Button] = {}
		self.result_grid: tk.Frame | None = None
		self.result_header_label: tk.Label | None = None
		self.timeline_canvases: list[tk.Canvas] = []
		self.current_player_options: list[str] = []
		self.current_bench_options: list[str] = []
		self.initial_player_options_home: list[str] = []
		self.initial_player_options_away: list[str] = []
		self.initial_bench_options_home: list[str] = []
		self.initial_bench_options_away: list[str] = []
		self.initial_player_id_map_home: dict[str, str] = {}
		self.initial_player_id_map_away: dict[str, str] = {}
		self.home_team_name = "홈팀"
		self.away_team_name = "어웨이팀"
		self.audio_supported = MediaPlayer is not None
		self.audio_volume_level = 0.8
		self.audio_resync_threshold_seconds = 0.35

		# Cached video panel pixel dimensions — updated via <Configure> to avoid winfo calls per frame.
		self._video_panel_width: int = 0
		self._video_panel_height: int = 0
		# Counter throttles seek-bar / time-label updates to ~15 fps during playback.
		self._playback_ui_skip_counter: int = 0
		# Counter triggers periodic audio resync (~every 2 s) without blocking the render loop.
		self._audio_resync_counter: int = 0

		self._build_styles()
		self._build_layout()
		self._bind_shortcuts()
		self.protocol("WM_DELETE_WINDOW", self._on_close)
		self.after(15, self._tick)

	def _bind_shortcuts(self) -> None:
		self.bind("<space>", self._on_space_key)
		self.bind("<Left>", self._on_left_key)
		self.bind("<Right>", self._on_right_key)
		self.bind("<Tab>", self._on_tab_key)
		self.bind("<Control-s>", self._on_ctrl_s)
		self.bind("<Control-S>", self._on_ctrl_s)
		self.bind("<BackSpace>", self._on_backspace_key)
		self.bind("<KeyPress>", self._on_key_press)
		self.focus_set()

	def _should_ignore_shortcut_event(self, event: tk.Event) -> bool:
		widget = getattr(event, "widget", None)
		if widget is None:
			return False
		return isinstance(widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox, tk.Spinbox))

	def _get_player_key_index(self, event: tk.Event) -> int | None:
		keysym = str(getattr(event, "keysym", "") or "")
		char = str(getattr(event, "char", "") or "")
		raw_keycode = getattr(event, "keycode", -1)
		try:
			keycode = int(raw_keycode)
		except (TypeError, ValueError):
			keycode = -1

		# Windows에서는 키패드가 KP_* 대신 일반 숫자 keysym으로 들어오는 경우가 있어 keycode도 함께 사용한다.
		keypad_player_keycode_map = {
			103: 0,  # NumPad7 / Home
			104: 1,  # NumPad8 / Up
			105: 2,  # NumPad9 / Prior
			100: 3,  # NumPad4 / Left
			101: 4,  # NumPad5 / Clear
			102: 5,  # NumPad6 / Right
			97: 6,   # NumPad1 / End
			98: 7,   # NumPad2 / Down
			99: 8,   # NumPad3 / Next
			96: 9,   # NumPad0 / Insert
			110: 10, # NumPadDecimal / Delete
			36: 0,   # Home (NumLock off)
			38: 1,   # Up (NumLock off)
			33: 2,   # Prior/PageUp (NumLock off)
			37: 3,   # Left (NumLock off)
			12: 4,   # Clear (NumLock off)
			39: 5,   # Right (NumLock off)
			35: 6,   # End (NumLock off)
			40: 7,   # Down (NumLock off)
			34: 8,   # Next/PageDown (NumLock off)
			45: 9,   # Insert (NumLock off)
			46: 10,  # Delete (NumLock off)
		}
		if keycode in keypad_player_keycode_map:
			return keypad_player_keycode_map[keycode]

		keypad_player_key_map = {
			"KP_7": 0,
			"KP_8": 1,
			"KP_9": 2,
			"KP_4": 3,
			"KP_5": 4,
			"KP_6": 5,
			"KP_1": 6,
			"KP_2": 7,
			"KP_3": 8,
			"KP_0": 9,
			"KP_Decimal": 10,
			# NumLock이 꺼진 상태에서도 같은 레이아웃 순서가 유지되도록 대응
			"KP_Home": 0,
			"KP_Up": 1,
			"KP_Prior": 2,
			"KP_Left": 3,
			"KP_Begin": 4,
			"KP_Right": 5,
			"KP_End": 6,
			"KP_Down": 7,
			"KP_Next": 8,
			"KP_Insert": 9,
			"KP_Delete": 10,
		}
		if keysym in keypad_player_key_map:
			return keypad_player_key_map[keysym]

		player_key_map = {
			"1": 0,
			"2": 1,
			"3": 2,
			"4": 3,
			"5": 4,
			"6": 5,
			"7": 6,
			"8": 7,
			"9": 8,
			"0": 9,
			"minus": 10,
			"equal": 11,
		}
		if keysym in player_key_map:
			return player_key_map[keysym]
		if char in "1234567890":
			return int(char) - 1 if char != "0" else 9
		if char in ("-", "_"):
			return 10
		if char in ("=", "+"):
			return 11
		return None

	def _get_action_key_index(self, event: tk.Event) -> int | None:
		char = str(getattr(event, "char", "") or "").lower()
		if not char:
			return None
		base_map = {
			"q": 0,
			"w": 1,
			"e": 2,
			"a": 3,
			"s": 4,
			"d": 5,
			"z": 6,
			"x": 7,
			"c": 8,
			"v": 9,
			"b": 10,
			"n": 11,
		}
		index = base_map.get(char)
		if index is None:
			return None

		# z/x/c를 빠르게 두 번 누르면 v/b/n 슬롯과 동일하게 취급한다.
		if char in ("z", "x", "c"):
			now = time.perf_counter()
			last = self._action_key_last_press.get(char, 0.0)
			self._action_key_last_press[char] = now
			if now - last <= 0.35:
				double_press_map = {"z": 9, "x": 10, "c": 11}
				return double_press_map[char]
		return index

	def _handle_number_selection(self, index: int) -> str:
		# ❌ 아래의 특수 동작 블록을 통째로 삭제하거나 주석 처리하세요.
		# if index == 1 and self.selected_player is None and self.selected_action is None:
		# 	if self.video_capture is not None:
		# 		self.selected_action = "북마크"
		# 		self._record_action_result("클립생성")
		# 		return "break"

		# 액션이 북마크일 때는 1=스크린샷, 2=클립생성 단축키로 동작
		if self.selected_action == "북마크":
			if index == 0:
				self._record_action_result("스크린샷")
				return "break"
			elif index == 1:
				self._record_action_result("클립생성")
				return "break"
			else:
				self.status_var.set(f"북마크 단축키는 1(스크린샷), 2(클립생성)만 지원합니다: {index + 1}")
				return "break"

		# 결과 선택 중이면 결과로 처리
		if self.selected_player and self.selected_action:
			result_options = ACTION_RESULT_OPTIONS.get(self.selected_action, [])
			if 0 <= index < len(result_options):
				self._record_action_result(result_options[index])
				return "break"
			self.status_var.set(f"결과 단축키 범위를 벗어났습니다: {index + 1}")
			return "break"

		# 선수 선택
		if 0 <= index < len(self.current_player_options):
			self._select_player(self.current_player_options[index])
			return "break"

		self.status_var.set(f"선수 단축키 범위를 벗어났습니다: {index + 1}")
		return "break"

	def _on_key_press(self, event: tk.Event) -> str | None:
		if self._should_ignore_shortcut_event(event):
			return None

		player_index = self._get_player_key_index(event)
		if player_index is not None:
			return self._handle_number_selection(player_index)

		action_index = self._get_action_key_index(event)
		if action_index is None:
			return None
		if 0 <= action_index < len(ACTION_OPTIONS):
			self._select_action(ACTION_OPTIONS[action_index])
			return "break"
		self.status_var.set(f"액션 단축키 범위를 벗어났습니다: {action_index + 1}")
		return "break"

	def _on_tab_key(self, event: tk.Event) -> str:
		if self._should_ignore_shortcut_event(event):
			return "break"
		next_team = "어웨이" if self.selected_team == "홈" else "홈"
		self._select_team(next_team)
		return "break"

	def _on_ctrl_s(self, _event: tk.Event) -> str:
		self._save_project()
		return "break"

	def _on_backspace_key(self, event: tk.Event) -> str | None:
		if self._should_ignore_shortcut_event(event):
			return None
		if self.selected_action is not None:
			self._select_action(None)
			self.status_var.set("액션 선택 취소")
			return "break"
		if self.selected_player is not None:
			self._select_player(None)
			self.status_var.set("선수 선택 취소")
			return "break"
		return "break"

	def _apply_window_icon(self) -> None:
		if not THUMBNAIL_ICON_PATH.exists():
			return
		try:
			self.iconbitmap(str(THUMBNAIL_ICON_PATH))
		except Exception:
			pass
		if sys.platform.startswith("win"):
			apply_windows_taskbar_icon(self, THUMBNAIL_ICON_PATH)

	def _build_styles(self) -> None:
		style = ttk.Style(self)
		try:
			style.theme_use("clam")
		except tk.TclError:
			pass
		style.configure("TFrame", background=WINDOW_BG)
		style.configure("Panel.TFrame", background=PANEL_BG)
		style.configure("Card.TFrame", background=CARD_BG)
		style.configure("TLabel", background=WINDOW_BG, foreground=TEXT_MAIN)
		style.configure("Muted.TLabel", background=WINDOW_BG, foreground=TEXT_MUTED)
		style.configure("Card.TLabel", background=CARD_BG, foreground=TEXT_MAIN)
		style.configure("TButton", padding=(12, 8))
		style.configure("Timeline.Horizontal.TScale", background=WINDOW_BG)
		style.configure("Record.Treeview", font=("Segoe UI", 8), rowheight=18)
		style.configure("Record.Treeview.Heading", font=("Segoe UI", 8, "bold"))

	def _build_layout(self) -> None:
		control_bar = ttk.Frame(self, style="Panel.TFrame")
		control_bar.pack(fill="x", padx=12, pady=(0, 8))

		self.open_button = tk.Button(
			control_bar,
			text="영상 불러오기",
			command=self.open_video_file,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.open_button.pack(side="left", padx=(0, 8))

		self.load_project_button = tk.Button(
			control_bar,
			text="프로젝트 불러오기",
			command=self.load_project,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.load_project_button.pack(side="left", padx=(0, 8))

		self.fotmob_lineup_button = tk.Button(
			control_bar,
			text="FotMob 명단 불러오기",
			command=self.import_lineups_from_fotmob_url,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.fotmob_lineup_button.pack(side="left", padx=(0, 8))

		self.record_button = tk.Button(
			control_bar,
			text="현재 시점 기록",
			command=self.record_current_view,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.record_button.pack(side="left", padx=(0, 8))

		self.timeline_offset_button = tk.Button(
			control_bar,
			text="시작 시각 조정",
			command=self._set_timeline_start_offset,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=12,
			pady=8,
		)
		self.timeline_offset_button.pack(side="left", padx=(0, 8))

		self.first_half_start_button = tk.Button(
			control_bar,
			text="전반 시작",
			command=self._mark_first_half_start,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=12,
			pady=8,
		)
		self.first_half_start_button.pack(side="left", padx=(0, 6))

		self.first_half_end_button = tk.Button(
			control_bar,
			text="전반 끝",
			command=self._mark_first_half_end,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=12,
			pady=8,
		)
		self.first_half_end_button.pack(side="left", padx=(0, 6))

		self.second_half_start_button = tk.Button(
			control_bar,
			text="후반 시작",
			command=self._mark_second_half_start,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=12,
			pady=8,
		)
		self.second_half_start_button.pack(side="left", padx=(0, 6))

		self.second_half_end_button = tk.Button(
			control_bar,
			text="후반 끝",
			command=self._mark_second_half_end,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=12,
			pady=8,
		)
		self.second_half_end_button.pack(side="left", padx=(0, 8))

		self.play_button = tk.Button(
			control_bar,
			text="재생",
			command=self.toggle_playback,
			bg=ACCENT,
			fg="#081017",
			relief="flat",
			activebackground="#27d081",
			activeforeground="#081017",
			padx=18,
			pady=8,
		)
		self.play_button.pack(side="left", padx=(0, 8))

		self.stop_button = tk.Button(
			control_bar,
			text="정지",
			command=self.stop_video,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.stop_button.pack(side="left", padx=(0, 8))

		self.time_label = tk.Label(
			control_bar,
			text="00:00 / 00:00",
			bg=PANEL_BG,
			fg=TEXT_MAIN,
			font=("Segoe UI", 10, "bold"),
		)
		self.time_label.pack(side="right")

		seek_row = ttk.Frame(self, style="Panel.TFrame")
		seek_row.pack(fill="x", padx=12, pady=(0, 8))
		seek_row.columnconfigure(1, weight=1)

		self.timeline_adjust_button = tk.Button(
			seek_row,
			text="타임라인 조정: 전체",
			command=self._toggle_timeline_adjust_mode,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=10,
			pady=6,
		)
		self.timeline_adjust_button.grid(row=0, column=0, sticky="w", padx=(0, 10))

		self.seek_scale = ttk.Scale(
			seek_row,
			from_=0.0,
			to=1.0,
			orient="horizontal",
			command=self._on_seek_change,
			style="Timeline.Horizontal.TScale",
		)
		self.seek_scale.grid(row=0, column=1, sticky="ew")
		self.seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
		self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

		content_row = ttk.Frame(self, style="Panel.TFrame")
		content_row.pack(fill="both", expand=True, padx=12, pady=(0, 8))
		content_row.columnconfigure(0, weight=1)
		content_row.rowconfigure(0, weight=1)

		left_content = ttk.Frame(content_row, style="Panel.TFrame")
		left_content.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
		left_content.rowconfigure(0, weight=1)
		left_content.columnconfigure(0, weight=1)

		video_area = ttk.Frame(left_content, style="Panel.TFrame")
		video_area.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
		video_area.rowconfigure(0, weight=1)
		video_area.columnconfigure(0, weight=1)

		self.video_panel = tk.Label(
			video_area,
			bg="black",
			fg=TEXT_MAIN,
			text="영상이 선택되면 여기에 표시됩니다",
			font=("Segoe UI", 16, "bold"),
			compound="center",
		)
		self.video_panel.grid(row=0, column=0, sticky="nsew")
		self.video_panel.bind("<Configure>", self._on_video_panel_resize)

		volume_panel = tk.Frame(video_area, bg=PANEL_BG)
		volume_panel.grid(row=0, column=1, sticky="ew", padx=(10, 0))
		self.volume_label = tk.Label(
			volume_panel,
			text="볼\n륨",
			bg=PANEL_BG,
			fg=TEXT_MUTED,
			font=("Segoe UI", 8, "bold"),
		)
		self.volume_label.pack(side="top", pady=(0, 4))
		self.volume_scale = tk.Scale(
			volume_panel,
			from_=100,
			to=0,
			orient="vertical",
			command=self._on_volume_change,
			showvalue=False,
			length=200,
			resolution=1,
			highlightthickness=0,
			bd=0,
			troughcolor="#2a3a45",
			bg=PANEL_BG,
			fg=TEXT_MAIN,
			activebackground=ACCENT,
		)
		self.volume_scale.set(int(self.audio_volume_level * 100))
		self.volume_scale.pack(side="top", fill="y", expand=True)

		self.timeline_canvas = self._create_timeline_canvas(left_content)
		self.timeline_canvas.grid(row=1, column=0, sticky="ew", pady=(0, 8))

		self.secondary_timeline_canvas = self._create_timeline_canvas(left_content)
		self.secondary_timeline_canvas.grid(row=2, column=0, sticky="ew", pady=(0, 10))

		self.sidebar_frame = ttk.Frame(content_row, style="Panel.TFrame", width=390)
		self.sidebar_frame.grid(row=0, column=1, sticky="nsew")
		self.sidebar_frame.pack_propagate(False)
		self._build_quick_record_panel(self.sidebar_frame)

		sidebar_bottom = ttk.Frame(self.sidebar_frame, style="Panel.TFrame")
		sidebar_bottom.pack(fill="both", expand=True, pady=(10, 0))
		self._build_record_list_section(sidebar_bottom)

		status_row = ttk.Frame(self, style="Panel.TFrame")
		status_row.pack(fill="x", padx=12, pady=(0, 12))
		self.status_var = tk.StringVar(value="영상 없음")
		self.status_label = tk.Label(
			status_row,
			textvariable=self.status_var,
			bg=PANEL_BG,
			fg=TEXT_MUTED,
			anchor="w",
		)
		self.status_label.pack(fill="x")

	def _timeline_seconds(self, video_seconds: float) -> float:
		video = max(0.0, float(video_seconds))
		offset = max(0.0, float(self.timeline_start_offset_seconds))
		first_start = self.first_half_start_seconds
		second_start = self.second_half_start_seconds

		# 1. 전반 시작 마커 없이 후반 시작만 지정된 경우 (버그 수정 부분)
		if first_start is None and second_start is not None:
			if video >= second_start:
				return 45.0 * 60.0 + (video - second_start) # 45:00(2700초)으로 매핑
			return max(0.0, video + offset)

		# 2. 둘 다 지정되지 않은 경우
		if first_start is None:
			return max(0.0, video + offset)

		# 3. 전반 시작 마커가 있는 경우
		first_start = max(0.0, float(first_start))
		if second_start is not None:
			second_start = max(first_start, float(second_start))

		if video <= first_start:
			return offset
		if second_start is not None and video >= second_start:
			return 45.0 * 60.0 + max(0.0, video - second_start)
		return max(offset, video - first_start + offset)

	def _video_seconds_from_timeline(self, timeline_seconds: float) -> float:
		timeline = max(0.0, float(timeline_seconds))
		offset = max(0.0, float(self.timeline_start_offset_seconds))
		first_start = self.first_half_start_seconds
		second_start = self.second_half_start_seconds

		# 1. 전반 시작 마커 없이 후반 시작만 지정된 경우 (버그 수정 부분)
		if first_start is None and second_start is not None:
			if timeline >= 45.0 * 60.0:
				return second_start + (timeline - 45.0 * 60.0)
			return max(0.0, timeline - offset)

		# 2. 둘 다 지정되지 않은 경우
		if first_start is None:
			return max(0.0, timeline - offset)

		# 3. 전반 시작 마커가 있는 경우
		first_start = max(0.0, float(first_start))
		if second_start is not None:
			second_start = max(first_start, float(second_start))

		if second_start is not None and timeline >= 45.0 * 60.0:
			return second_start + (timeline - 45.0 * 60.0)
		return first_start + max(0.0, timeline - offset)

	def _set_timeline_start_offset(self) -> None:
		current_text = format_time(self.timeline_start_offset_seconds)
		raw_value = simpledialog.askstring(
			"타임라인 조정",
			"타임라인 기준 시각을 입력하세요.\n예: 녹화를 전반 6분부터 시작했다면 6 또는 6:00\n(지원: 70, 70:00, 01:10:00)",
			parent=self,
			initialvalue=current_text,
		)
		if raw_value is None:
			return

		try:
			offset_seconds = parse_timeline_offset_input(raw_value)
		except ValueError as error:
			messagebox.showwarning("타임라인 조정", str(error), parent=self)
			return

		self.timeline_start_offset_seconds = offset_seconds
		
		# 오프셋 변경 시에도 교체 기록 시간 재계산 및 선수 버튼 갱신
		self._sync_fotmob_records()
		self._rebuild_lineups_from_records(self.current_time_seconds)
		
		self._update_time_label()
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set(f"타임라인 조정 적용: {format_time(self.timeline_start_offset_seconds)}")

	def _mark_first_half_start(self) -> None:
		self._mark_period_boundary("전반 시작", "first_half_start_seconds")

	def _mark_first_half_end(self) -> None:
		self._mark_period_boundary("전반 끝", "first_half_end_seconds")

	def _mark_second_half_start(self) -> None:
		self._mark_period_boundary("후반 시작", "second_half_start_seconds")

	def _mark_second_half_end(self) -> None:
		self._mark_period_boundary("후반 끝", "second_half_end_seconds")

	def _mark_period_boundary(self, label: str, attr_name: str) -> None:
		if self.video_capture is None:
			messagebox.showwarning("타임라인 구간", "먼저 영상을 불러오세요.", parent=self)
			return
		setattr(self, attr_name, float(self.current_time_seconds))
		
		# 시간대가 변했으므로 교체 기록들을 새 기준에 맞게 업데이트하고 선수 버튼 갱신
		self._sync_fotmob_records()
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._refresh_record_tree()
		
		self._redraw_timeline()
		self.status_var.set(f"{label} 지정: {format_time(self._timeline_seconds(self.current_time_seconds))}")

	def _toggle_timeline_adjust_mode(self) -> None:
		self.timeline_adjust_mode = not self.timeline_adjust_mode
		button_text = "타임라인 조정: 전후반" if self.timeline_adjust_mode else "타임라인 조정: 전체"
		self.timeline_adjust_button.configure(text=button_text)
		self._redraw_timeline()
		self.status_var.set("타임라인 조정 모드: 전후반" if self.timeline_adjust_mode else "타임라인 조정 모드: 전체")

	def _get_marker_times(self) -> list[tuple[str, float, str]]:
		markers: list[tuple[str, float, str]] = []
		for label, value, color in (
			("전반 시작", self.first_half_start_seconds, "#87e8a9"),
			("전반 끝", self.first_half_end_seconds, "#87e8a9"),
			("후반 시작", self.second_half_start_seconds, "#ffd166"),
			("후반 끝", self.second_half_end_seconds, "#ffd166"),
		):
			if value is not None and self.duration_seconds > 0:
				markers.append((label, clamp(float(value), 0.0, self.duration_seconds), color))
		return markers

	def _resolve_timeline_ranges(self) -> dict[tk.Canvas, tuple[float, float, str]]:
		ranges: dict[tk.Canvas, tuple[float, float, str]] = {}
		if not self.timeline_canvases:
			return ranges

		duration = max(0.0, self.duration_seconds)
		if duration <= 0:
			for index, canvas in enumerate(self.timeline_canvases):
				label = "전반" if index == 0 else "후반"
				ranges[canvas] = (0.0, 0.0, label)
			return ranges

		if not self.timeline_adjust_mode:
			for index, canvas in enumerate(self.timeline_canvases):
				label = "전체 타임라인" if index == 0 else "전체 타임라인 (보조)"
				ranges[canvas] = (0.0, duration, label)
			return ranges

		first_start = clamp(self.first_half_start_seconds if self.first_half_start_seconds is not None else 0.0, 0.0, duration)
		second_start_explicit = clamp(self.second_half_start_seconds, 0.0, duration) if self.second_half_start_seconds is not None else None

		if self.first_half_end_seconds is not None:
			first_end_raw = self.first_half_end_seconds
		elif second_start_explicit is not None:
			first_end_raw = second_start_explicit
		else:
			first_end_raw = duration
		first_end = clamp(first_end_raw, 0.0, duration)
		if first_end <= first_start:
			first_start, first_end = 0.0, duration

		if second_start_explicit is not None:
			second_start = second_start_explicit
		elif self.first_half_end_seconds is not None:
			second_start = clamp(self.first_half_end_seconds, 0.0, duration)
		else:
			second_start = first_end

		if self.second_half_end_seconds is not None:
			second_end = clamp(self.second_half_end_seconds, 0.0, duration)
		else:
			second_end = duration
		if second_end <= second_start:
			second_start, second_end = 0.0, duration

		for index, canvas in enumerate(self.timeline_canvases):
			if index == 0:
				ranges[canvas] = (first_start, first_end, "전반")
			else:
				ranges[canvas] = (second_start, second_end, "후반")
		return ranges

	def _period_label_from_markers(self, video_seconds: float) -> str:
		seconds = max(0.0, float(video_seconds))
		first_start = self.first_half_start_seconds
		first_end = self.first_half_end_seconds
		second_start = self.second_half_start_seconds
		second_end = self.second_half_end_seconds

		if second_start is not None and second_end is not None and second_start <= seconds <= second_end:
			return "후반"
		if second_start is not None and seconds >= second_start:
			return "후반"

		if first_start is not None:
			if first_end is not None:
				if first_start <= seconds <= first_end:
					return "전반"
			elif second_start is not None:
				if first_start <= seconds < second_start:
					return "전반"
			elif seconds >= first_start:
				return "전반"

		return ""

	def _build_quick_record_panel(self, parent: tk.Misc) -> None:
		panel = ttk.Frame(parent, style="Panel.TFrame")
		panel.pack(fill="both", expand=True)

		team_box = tk.Frame(panel, bg=WINDOW_BG)
		team_box.pack(fill="x", pady=(0, 10))
		ttk.Label(team_box, text="팀", style="Card.TLabel").pack(anchor="w", pady=(0, 6))
		team_grid = tk.Frame(team_box, bg=WINDOW_BG)
		team_grid.pack(fill="x")
		for index, team_label in enumerate(["홈", "어웨이"]):
			button = tk.Button(
				team_grid,
				text=team_label,
				command=lambda value=team_label: self._select_team(value),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=10,
				pady=8,
			)
			button.grid(row=0, column=index, sticky="ew", padx=4, pady=2)
			self.team_buttons[team_label] = button
		for column in range(2):
			team_grid.grid_columnconfigure(column, weight=1)

		player_box = tk.Frame(panel, bg=WINDOW_BG)
		player_box.pack(fill="x", pady=(0, 10))
		ttk.Label(player_box, text="선수", style="Card.TLabel").pack(anchor="w", pady=(0, 6))
		player_grid = tk.Frame(player_box, bg=WINDOW_BG)
		player_grid.pack(fill="x")
		self.player_grid_container = player_grid

		action_box = tk.Frame(panel, bg=WINDOW_BG)
		action_box.pack(fill="both", expand=True)
		ttk.Label(action_box, text="액션", style="Card.TLabel").pack(anchor="w", pady=(0, 6))
		action_grid = tk.Frame(action_box, bg=WINDOW_BG)
		action_grid.pack(fill="x", pady=(0, 10))
		for index, action_label in enumerate(ACTION_OPTIONS):
			button = tk.Button(
				action_grid,
				text=action_label,
				command=lambda value=action_label: self._select_action(value),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=9,
				pady=7,
			)
			button.grid(row=index // 3, column=index % 3, sticky="ew", padx=3, pady=3)
			self.action_buttons[action_label] = button
		for column in range(3):
			action_grid.grid_columnconfigure(column, weight=1)

		self.result_header_label = tk.Label(
			action_box,
			text="결과",
			bg=WINDOW_BG,
			fg=TEXT_MUTED,
			anchor="w",
			font=("Segoe UI", 9, "bold"),
		)
		self.result_header_label.pack(fill="x", pady=(0, 4))

		self.result_grid = tk.Frame(action_box, bg=WINDOW_BG)
		self.result_grid.pack(fill="x")
		self._rebuild_result_buttons()
		self._select_team("홈")
		self._set_quick_record_state("disabled")

	def _build_record_list_section(self, parent: tk.Misc) -> None:
		records_header = tk.Label(parent, text="기록 목록", bg=PANEL_BG, fg=TEXT_MAIN, anchor="w")
		records_header.pack(fill="x", pady=(0, 6))

		columns = ("time", "team", "player", "action")
		self.record_tree = ttk.Treeview(parent, columns=columns, show="headings", height=4, style="Record.Treeview")
		self.record_tree.heading("time", text="시각")
		self.record_tree.heading("team", text="팀")
		self.record_tree.heading("player", text="선수")
		self.record_tree.heading("action", text="행위")
		self.record_tree.column("time", width=54, anchor="center")
		self.record_tree.column("team", width=44, anchor="center")
		self.record_tree.column("player", width=170, anchor="w")
		self.record_tree.column("action", width=96, anchor="w")
		self.record_tree.pack(fill="x")
		self.record_tree.bind("<Double-1>", self._on_record_double_click)
		self.record_tree.bind("<Delete>", self._on_record_delete_key)

		record_actions_row = tk.Frame(parent, bg=PANEL_BG)
		record_actions_row.pack(fill="x", pady=(8, 0))

		self.delete_record_button = tk.Button(
			record_actions_row,
			text="선택 삭제",
			command=self._delete_selected_record,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=10,
			pady=6,
		)
		self.delete_record_button.pack(side="left", padx=(0, 4))

		self.clear_records_button = tk.Button(
			record_actions_row,
			text="전체 삭제",
			command=self._clear_all_records,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=10,
			pady=6,
		)
		self.clear_records_button.pack(side="left", padx=(0, 4))

		self.save_records_button = tk.Button(
			record_actions_row,
			text="CSV 저장",
			command=self._save_records,
			bg=ACCENT,
			fg="#081017",
			relief="flat",
			activebackground="#27d081",
			activeforeground="#081017",
			padx=10,
			pady=6,
		)
		self.save_records_button.pack(side="right")

		self.save_project_button = tk.Button(
			record_actions_row,
			text="프로젝트 저장",
			command=self._save_project,
			bg=ACCENT,
			fg="#081017",
			relief="flat",
			activebackground="#27d081",
			activeforeground="#081017",
			padx=10,
			pady=6,
		)
		self.save_project_button.pack(side="right", padx=(0, 4))

	def _create_timeline_canvas(self, parent: tk.Misc) -> tk.Canvas:
		canvas = tk.Canvas(parent, bg=CARD_BG, highlightthickness=0, height=92)
		canvas.bind("<Configure>", lambda _event: self._redraw_timeline())
		canvas.bind("<ButtonPress-1>", self._on_timeline_press)
		canvas.bind("<B1-Motion>", self._on_timeline_drag)
		canvas.bind("<ButtonRelease-1>", self._on_timeline_release)
		self.timeline_canvases.append(canvas)
		return canvas

	def open_video_file(self) -> None:
		if cv2 is None:
			show_error("영상 재생", "OpenCV(cv2)가 설치되어 있지 않습니다.")
			return

		selected_path = filedialog.askopenfilename(
			title="재생할 영상 선택",
			initialdir=get_default_video_initial_dir(),
			filetypes=VIDEO_FILETYPES,
		)
		if not selected_path:
			return
		self.load_video(Path(selected_path))

	def load_video(self, video_path: Path) -> None:
		self._release_video()

		capture = cv2.VideoCapture(str(video_path))
		if not capture.isOpened():
			show_error("영상 불러오기", f"영상을 열 수 없습니다.\n{video_path}")
			return

		fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
		if fps <= 0:
			fps = 30.0
		frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
		duration_seconds = frame_count / fps if frame_count > 0 else 0.0

		self.video_capture = capture
		self._create_audio_player(video_path)
		self.video_path = video_path
		self.video_fps = fps
		self.video_frame_count = frame_count
		self.duration_seconds = duration_seconds
		self.current_frame_index = 0
		self.current_time_seconds = 0.0
		self.playback_frame_accumulator = 0.0
		self.last_tick_time = time.perf_counter()
		self.is_playing = False
		self.is_scrubbing = False
		self.scrub_was_playing = False

		self.seek_scale.configure(to=max(self.duration_seconds, 0.1))
		self._set_seek_value(0.0)
		self._update_time_label()
		self.play_button.configure(text="재생")
		if hasattr(self, "record_button"):
			self.record_button.configure(state="normal")
		self._set_quick_record_state("normal")
		self._load_player_files()
		self._select_team("홈")
		self._rebuild_player_buttons()
		audio_status = "오디오 준비" if self.audio_player is not None else "오디오 없음"
		self.status_var.set(f"불러온 파일: {video_path.name} ({audio_status})")
		self.project_file_path = None
		self.last_saved_project_payload = None
		self._redraw_timeline()
		self._refresh_record_tree()

		first_frame_ok, first_frame = capture.read()
		if first_frame_ok:
			self.current_frame_index = 1
			self.current_time_seconds = 0.0
			self._display_frame(first_frame)
		else:
			self._show_placeholder("프레임을 읽을 수 없습니다")

	def _create_audio_player(self, video_path: Path) -> None:
		self._release_audio_player()
		if MediaPlayer is None:
			return
		try:
			self.audio_player = MediaPlayer(
				str(video_path),
				ff_opts={
					"paused": True,
					"vn": True,
					"sn": True,
					"sync": "audio",
				},
			)
			# Prime the pipeline — ffpyplayer requires at least one get_frame() call
			# before set_pause(False) will reliably start audio output.
			self.audio_player.get_frame()
		except Exception:
			self.audio_player = None
		self._apply_audio_volume()

	def _pump_audio_player(self) -> None:
		if self.audio_player is None or not self.is_playing:
			return
		for _ in range(3):
			try:
				_frame, value = self.audio_player.get_frame()
			except Exception:
				break
			if value == "eof":
				self.pause_video()
				self.current_time_seconds = self.duration_seconds
				self._set_seek_value(self.duration_seconds)
				self._update_time_label()
				break
			# With vn=True (audio-only mode) _frame is always None — that is expected.
			# Do not break on "paused": right after set_pause(False) the player may still
			# report "paused" for one or two calls while the state propagates internally.
			# Only stop pumping when there is genuinely no data ready yet.
			if _frame is None and value is None:
				break

	def _apply_audio_volume(self) -> None:
		if self.audio_player is None:
			return
		try:
			self.audio_player.set_volume(clamp(self.audio_volume_level, 0.0, 1.0))
		except Exception:
			pass

	def _seek_audio_player(self, seconds: float, *, accurate: bool) -> None:
		if self.audio_player is None:
			return
		try:
			self.audio_player.seek(max(0.0, float(seconds)), relative=False, accurate=accurate)
		except Exception:
			pass

	def _resync_audio_if_needed(self) -> None:
		if self.audio_player is None:
			return
		try:
			audio_pts = self.audio_player.get_pts()
		except Exception:
			audio_pts = None
		if audio_pts is None:
			return
		if abs(float(audio_pts) - self.current_time_seconds) >= self.audio_resync_threshold_seconds:
			self._seek_audio_player(self.current_time_seconds, accurate=True)

	def _on_volume_change(self, value: str) -> None:
		try:
			self.audio_volume_level = clamp(float(value) / 100.0, 0.0, 1.0)
		except (TypeError, ValueError):
			return
		self._apply_audio_volume()

	def _release_audio_player(self) -> None:
		if self.audio_player is None:
			return
		try:
			self.audio_player.set_pause(True)
		except Exception:
			pass
		try:
			self.audio_player.close_player()
		except Exception:
			pass
		self.audio_player = None

	def _release_video(self) -> None:
		self._release_audio_player()
		if self.video_capture is not None:
			self.video_capture.release()
		self.video_capture = None
		self.video_path = None
		self.video_fps = 30.0
		self.video_frame_count = 0
		self.duration_seconds = 0.0
		self.current_frame_index = 0
		self.current_time_seconds = 0.0
		self.timeline_adjust_mode = False
		self.first_half_start_seconds = None
		self.first_half_end_seconds = None
		self.second_half_start_seconds = None
		self.second_half_end_seconds = None
		self.timeline_canvas_ranges.clear()
		self.playback_frame_accumulator = 0.0
		self.is_playing = False
		self.is_scrubbing = False
		self.scrub_was_playing = False
		self.current_frame_photo = None
		self.play_button.configure(text="재생")
		if hasattr(self, "record_button"):
			self.record_button.configure(state="disabled")
		if hasattr(self, "timeline_adjust_button"):
			self.timeline_adjust_button.configure(text="타임라인 조정: 전체")
		self._set_quick_record_state("disabled")
		self._select_team("홈")
		self._select_player(None)
		self._select_action(None)
		self.timeline_records.clear()
		if hasattr(self, "record_tree"):
			self._refresh_record_tree()
		if hasattr(self, "timeline_canvas"):
			self._redraw_timeline()

	def toggle_playback(self) -> None:
		if self.video_capture is None:
			self.open_video_file()
			return
		if self.is_playing:
			self.pause_video()
		else:
			self.play_video()

	def play_video(self) -> None:
		if self.video_capture is None:
			return
		if self.audio_player is not None:
			self._resync_audio_if_needed()
			try:
				self.audio_player.set_pause(False)
				# Kick-start the pipeline immediately — don't wait for the next _tick.
				self.audio_player.get_frame()
			except Exception:
				pass
		self.is_playing = True
		self.last_tick_time = time.perf_counter()
		self.playback_frame_accumulator = 0.0
		self.play_button.configure(text="일시정지")
		if self.video_path is not None:
			self.status_var.set(f"재생 중: {self.video_path.name}")

	def pause_video(self) -> None:
		if self.video_capture is None:
			return
		if self.audio_player is not None:
			try:
				self.audio_player.set_pause(True)
			except Exception:
				pass
		self.is_playing = False
		self.play_button.configure(text="재생")
		if self.video_path is not None:
			self.status_var.set(f"일시정지: {self.video_path.name}")

	def stop_video(self) -> None:
		if self.video_capture is None:
			return
		self.pause_video()
		self.seek_to(0.0)

	def seek_relative(self, delta_seconds: float) -> None:
		if self.video_capture is None:
			return
		target = self.current_time_seconds + delta_seconds
		self.seek_to(target)

	def seek_to(self, seconds: float) -> None:
		if self.video_capture is None:
			return

		seconds = clamp(seconds, 0.0, self.duration_seconds if self.duration_seconds > 0 else seconds)
		target_frame = int(round(seconds * self.video_fps))
		if self.video_frame_count > 0:
			target_frame = min(max(target_frame, 0), self.video_frame_count - 1)
		else:
			target_frame = max(target_frame, 0)

		self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
		success, frame = self.video_capture.read()
		if success:
			self.current_frame_index = target_frame + 1
			self.current_time_seconds = min(self.duration_seconds, target_frame / self.video_fps if self.video_fps > 0 else seconds)
			self._display_frame(frame)
		else:
			self.current_frame_index = target_frame
			self.current_time_seconds = seconds
			self._show_placeholder("프레임을 표시할 수 없습니다")

		self.playback_frame_accumulator = 0.0
		self.last_tick_time = time.perf_counter()
		if self.audio_player is not None:
			self._seek_audio_player(self.current_time_seconds, accurate=True)
			try:
				self.audio_player.set_pause(not self.is_playing)
			except Exception:
				pass
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._set_seek_value(self.current_time_seconds)
		self._update_time_label()
		self._redraw_timeline()

	def _on_seek_press(self, _event: tk.Event) -> None:
		if self.video_capture is None:
			return
		self.is_scrubbing = True
		self.scrub_was_playing = self.is_playing
		if self.is_playing:
			self.pause_video()

	def _on_seek_release(self, _event: tk.Event) -> None:
		if self.video_capture is None:
			return
		self.is_scrubbing = False
		self.seek_to(float(self.seek_scale.get()))
		if self.scrub_was_playing:
			self.play_video()
		self.scrub_was_playing = False

	def _on_seek_change(self, value: str) -> None:
		if self.video_capture is None or self._updating_seek:
			return
		seconds = clamp(float(value), 0.0, self.duration_seconds if self.duration_seconds > 0 else float(value))
		self.current_time_seconds = seconds
		self._update_time_label()
		if not self.is_scrubbing and not self.is_playing:
			self.seek_to(seconds)

	def _open_record_dialog(self, seconds: float) -> None:
		if self.video_capture is None:
			return
		dialog = RecordDialog(self)
		if not getattr(dialog, "player_name", ""):
			return
		player_label = format_player_label(dialog.jersey_number, dialog.player_name)
		self.timeline_records.append(
			TimelineRecord(
				time_seconds=seconds,
				period_label=self._period_label_from_markers(seconds),
				team=dialog.team_name,
				jersey_number=dialog.jersey_number,
				player_id=self._resolve_player_id(dialog.team_name, player_label),
				player_name=dialog.player_name,
				action=dialog.action_name,
				result="",
			)
		)
		self.record_counter += 1
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set(f"현재 시점 기록: {format_time(self._timeline_seconds(seconds))} · {dialog.team_name} · {player_label} · {dialog.action_name}")

	def _load_player_files(self) -> None:
		script_dir = Path(__file__).parent
		home_file = script_dir / "players_home.txt"
		away_file = script_dir / "players_away.txt"
		global PLAYER_OPTIONS_HOME, PLAYER_OPTIONS_AWAY, BENCH_OPTIONS_HOME, BENCH_OPTIONS_AWAY
		global PLAYER_ID_MAP_HOME, PLAYER_ID_MAP_AWAY
		home_starting, home_bench = load_players_from_file(str(home_file))
		away_starting, away_bench = load_players_from_file(str(away_file))
		self.initial_player_options_home = list(home_starting)
		self.initial_bench_options_home = list(home_bench)
		self.initial_player_options_away = list(away_starting)
		self.initial_bench_options_away = list(away_bench)
		PLAYER_OPTIONS_HOME = list(home_starting)
		BENCH_OPTIONS_HOME = list(home_bench)
		PLAYER_OPTIONS_AWAY = list(away_starting)
		BENCH_OPTIONS_AWAY = list(away_bench)
		PLAYER_ID_MAP_HOME = dict(self.initial_player_id_map_home)
		PLAYER_ID_MAP_AWAY = dict(self.initial_player_id_map_away)

	def _resolve_player_id(self, team: str, player_label: str) -> str:
		if team == "홈":
			player_id_map = PLAYER_ID_MAP_HOME
		else:
			player_id_map = PLAYER_ID_MAP_AWAY
		return _resolve_player_id_from_map(player_label, player_id_map)

	def _resolve_team_name(self, team: str) -> str:
		if team == "홈":
			return self.home_team_name
		if team == "어웨이":
			return self.away_team_name
		return team or ""

	def import_lineups_from_fotmob_url(self) -> None:
		match_url = simpledialog.askstring(
			"FotMob 명단 불러오기",
			"FotMob 경기 URL을 입력하세요.\n예: https://www.fotmob.com/matches/girona-vs-real-madrid/27qfz8#4837419",
			parent=self,
		)
		if match_url is None:
			return
		match_url = match_url.strip()
		if not match_url:
			messagebox.showwarning("FotMob 명단 불러오기", "URL을 입력하세요.", parent=self)
			return

		try:
			match_id = parse_fotmob_match_id(match_url)
			lineups = fetch_fotmob_lineups(match_id, match_url)
			html_lineups = _extract_lineups_from_match_html(match_url, match_id)
			for key, value in html_lineups.get("home_player_id_map", {}).items():
				lineups.setdefault("home_player_id_map", {})
				lineups["home_player_id_map"].setdefault(key, value)
			for key, value in html_lineups.get("away_player_id_map", {}).items():
				lineups.setdefault("away_player_id_map", {})
				lineups["away_player_id_map"].setdefault(key, value)
		except Exception as error:
			messagebox.showerror(
				"FotMob 명단 불러오기",
				f"명단을 불러오지 못했습니다.\n{error}",
				parent=self,
			)
			return

		script_dir = Path(__file__).parent
		home_file = script_dir / "players_home.txt"
		away_file = script_dir / "players_away.txt"
		global PLAYER_ID_MAP_HOME, PLAYER_ID_MAP_AWAY
		try:
			save_lineup_file(home_file, lineups["home_starting"], lineups["home_bench"])
			save_lineup_file(away_file, lineups["away_starting"], lineups["away_bench"])
		except OSError as error:
			messagebox.showerror(
				"FotMob 명단 저장",
				f"명단 파일 저장에 실패했습니다.\n{error}",
				parent=self,
			)
			return

		PLAYER_ID_MAP_HOME = dict(lineups.get("home_player_id_map", {}))
		PLAYER_ID_MAP_AWAY = dict(lineups.get("away_player_id_map", {}))
		self.home_team_name = str(lineups.get("home_team_name", "") or "홈팀")
		self.away_team_name = str(lineups.get("away_team_name", "") or "어웨이팀")
		self.initial_player_id_map_home = dict(PLAYER_ID_MAP_HOME)
		self.initial_player_id_map_away = dict(PLAYER_ID_MAP_AWAY)
		self._load_player_files()
		PLAYER_ID_MAP_HOME = dict(self.initial_player_id_map_home)
		PLAYER_ID_MAP_AWAY = dict(self.initial_player_id_map_away)
		auto_home_sub_count = self._append_fotmob_substitution_records("홈", lineups.get("home_substitutions", []))
		auto_away_sub_count = self._append_fotmob_substitution_records("어웨이", lineups.get("away_substitutions", []))
		auto_sub_count = auto_home_sub_count + auto_away_sub_count
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._refresh_record_tree()
		self._redraw_timeline()
		self._select_team("홈")

		home_count = len(lineups["home_starting"])
		away_count = len(lineups["away_starting"])
		home_bench_count = len(lineups["home_bench"])
		away_bench_count = len(lineups["away_bench"])
		messagebox.showinfo(
			"FotMob 명단 불러오기",
			(
				f"저장 완료\n\n"
				f"홈팀: {lineups['home_team_name']} (선발 {home_count}, 교체 {home_bench_count})\n"
				f"어웨이팀: {lineups['away_team_name']} (선발 {away_count}, 교체 {away_bench_count})\n\n"
				f"자동 교체 기록 추가: {auto_sub_count}개\n"
				f"(CSV 자동 생성 없음)\n\n"
				f"저장 파일:\n{home_file.name}, {away_file.name}"
			),
			parent=self,
		)
		self.status_var.set(
			f"FotMob 명단 업데이트: {lineups['home_team_name']} vs {lineups['away_team_name']}"
		)

	def _apply_substitution_to_lineups(self, team: str, out_player: str, in_player: str) -> None:
		global PLAYER_OPTIONS_HOME, PLAYER_OPTIONS_AWAY, BENCH_OPTIONS_HOME, BENCH_OPTIONS_AWAY
		if team == "홈":
			starting = PLAYER_OPTIONS_HOME
			bench = BENCH_OPTIONS_HOME
		else:
			starting = PLAYER_OPTIONS_AWAY
			bench = BENCH_OPTIONS_AWAY

		# 1차 검색: 이름 라벨 매칭
		out_index = _find_player_label_index(starting, out_player)
		in_index = _find_player_label_index(bench, in_player)

		# 2차 검색: 선수 고유 ID(player_id)를 이용한 매칭 (가장 정확함)
		if out_index < 0:
			out_player_id = self._resolve_player_id(team, out_player)
			if out_player_id:  # 고유 ID를 성공적으로 가져왔을 때
				for idx, cand in enumerate(starting):
					cand_id = self._resolve_player_id(team, cand)
					if cand_id == out_player_id:
						out_index = idx
						break

		# 3차 검색: ID도 없다면 등번호를 이용한 최후의 매칭
		if out_index < 0:
			out_jersey, _ = split_player_label(out_player)
			if out_jersey:
				for idx, cand in enumerate(starting):
					cand_jersey, _ = split_player_label(cand)
					if cand_jersey == out_jersey:
						out_index = idx
						break

		# 어떻게든 선발에서 나갈 선수를 찾지 못했다면 취소
		if out_index < 0:
			return

		# 벤치 명단에 들어오는 선수가 없더라도(in_index < 0), 교체는 강제로 진행!
		actual_in_player = bench[in_index] if in_index >= 0 else in_player
		actual_out_player = starting[out_index]

		# 선발 명단 업데이트 (UI 버튼에 반영될 데이터)
		starting[out_index] = actual_in_player

		# 벤치 명단 업데이트
		if in_index >= 0:
			bench[in_index] = actual_out_player
		else:
			# 벤치에 없던 선수가 들어왔다면 벤치 리스트에 아웃된 선수를 새로 추가
			bench.append(actual_out_player)

	def _append_fotmob_substitution_records(self, team: str, substitutions: list[dict]) -> int:
		added_count = 0
		for substitution in substitutions:
			if not isinstance(substitution, dict):
				continue
			out_player = str(substitution.get("out_player", "")).strip()
			in_player = str(substitution.get("in_player", "")).strip()
			minute = _to_int_minutes(substitution.get("source_minute", substitution.get("minute")))
			if not out_player or not in_player or minute is None:
				continue
			display_minute = _to_int_minutes(substitution.get("display_minute"))
			if display_minute is None:
				display_minute = _normalize_fotmob_substitution_minute(minute)
			period_label = _normalize_fotmob_period_label(substitution.get("period_label")) or _fotmob_period_label_from_substitution_minute(minute)

			timeline_seconds = float(max(0, display_minute) * 60)
			original_timeline_seconds = float(max(0, minute) * 60)
			seconds = self._video_seconds_from_timeline(timeline_seconds)
			original_seconds = self._video_seconds_from_timeline(original_timeline_seconds)
			out_jersey, out_name = split_player_label(out_player)
			in_jersey, in_name = split_player_label(in_player)
			if not out_name or not in_name:
				continue
			out_player_id = str(substitution.get("fotmob_sub_out_player_id", "") or "").strip() or self._resolve_player_id(team, out_player)
			in_player_id = str(substitution.get("fotmob_sub_in_player_id", "") or "").strip() or self._resolve_player_id(team, in_player)

			matching_record = next(
				(
					record
					for record in self.timeline_records
					if record.action == "교체"
					and record.team == team
					and (abs(record.time_seconds - seconds) < 0.5 or abs(record.time_seconds - original_seconds) < 0.5)
					and record.sub_out_player_name == out_name
					and record.sub_in_player_name == in_name
				),
				None,
			)
			if matching_record is not None:
				if period_label and not matching_record.period_label:
					matching_record.period_label = period_label
				matching_record.player_id = "FOTMOB_AUTO"
				matching_record.fotmob_minute = display_minute
				continue

			new_record = TimelineRecord(
				time_seconds=seconds,
				period_label=period_label,
				team=team,
				jersey_number="",
				player_id="FOTMOB_AUTO",  # 자동 기록임을 식별하는 태그 추가
				player_name="",
				action="교체",
				result="",
				sub_out_jersey_number=out_jersey,
				sub_out_player_id=out_player_id,
				sub_out_player_name=out_name,
				sub_in_jersey_number=in_jersey,
				sub_in_player_id=in_player_id,
				sub_in_player_name=in_name,
			)
			new_record.fotmob_minute = display_minute  # 기준 분 저장
			self.timeline_records.append(new_record)
			added_count += 1

		return added_count

	def _write_records_to_csv(self, target_path: Path) -> None:
		with open(target_path, "w", newline="", encoding="utf-8-sig") as csv_file:
			writer = csv.writer(csv_file)
			writer.writerow([
				"time_seconds",
				"video_time_seconds",
				"period_label",
				"time_text",
				"team_name",
				"home_away",
				"jersey_number",
				"player_id",
				"player_name",
				"action",
				"result",
				"sub_out_jersey_number",
				"sub_out_player_id",
				"sub_out_player_name",
				"sub_in_jersey_number",
				"sub_in_player_id",
				"sub_in_player_name",
			])
			records = list(enumerate(self.timeline_records))
			records.sort(key=lambda item: (item[1].time_seconds, item[0]))
			for _, record in records:
				action_value = record.action
				result_value = record.result
				jersey_value = record.jersey_number
				player_id_value = record.player_id
				player_name_value = record.player_name
				sub_out_jersey_value = record.sub_out_jersey_number
				sub_out_player_id_value = record.sub_out_player_id
				sub_out_name_value = record.sub_out_player_name
				sub_in_jersey_value = record.sub_in_jersey_number
				sub_in_player_id_value = record.sub_in_player_id
				sub_in_name_value = record.sub_in_player_name
				team_value = record.team or "우리팀"
				team_name_value = self._resolve_team_name(team_value)
				# Legacy data safety: split combined text like "액션 · 결과" if result is empty.
				if not result_value and " · " in action_value:
					action_value, result_value = action_value.split(" · ", 1)
				if action_value == "교체" and (not sub_out_name_value or not sub_in_name_value) and "->" in result_value:
					left, right = result_value.split("->", 1)
					sub_out_jersey_value, sub_out_name_value = split_player_label(left.strip())
					sub_in_jersey_value, sub_in_name_value = split_player_label(right.strip())
					result_value = ""
				if action_value == "교체" and not sub_in_player_id_value and sub_in_name_value:
					sub_in_label = format_player_label(sub_in_jersey_value, sub_in_name_value)
					sub_in_player_id_value = self._resolve_player_id(team_value, sub_in_label)
					record.sub_in_player_id = sub_in_player_id_value
				if action_value == "교체":
					jersey_value = ""
					player_id_value = ""
					player_name_value = ""
				if action_value != "교체" and not jersey_value and player_name_value:
					legacy_jersey, legacy_name = split_player_label(player_name_value)
					if legacy_jersey:
						jersey_value = legacy_jersey
						player_name_value = legacy_name
				period_label_value = record.period_label or self._period_label_from_markers(record.time_seconds)
				# 저장 경로(스크린샷/클립 등)는 result에 포함하지 않고, 오직 입력한 코멘트만 저장
				pure_result = result_value
				# 북마크+스크린샷/클립생성: result에 '스크린샷 저장:' 등으로 시작하면 빈 문자열로 저장
				if action_value == "북마크" and (
					(result_value and (result_value.startswith("스크린샷 저장:") or result_value.startswith("클립 저장됨:") or result_value.startswith("FFmpeg 없음") or result_value.startswith("저장 실패")))
				):
					pure_result = ""
				# action/result를 별도 열로 저장
				writer.writerow([
					round(self._timeline_seconds(record.time_seconds), 3),
					round(record.time_seconds, 3),
					period_label_value,
					format_time_for_csv(self._timeline_seconds(record.time_seconds)),
					team_name_value,
					team_value,
					jersey_value,
					player_id_value,
					player_name_value,
					action_value,
					pure_result,
					sub_out_jersey_value,
					sub_out_player_id_value,
					sub_out_name_value,
					sub_in_jersey_value,
					sub_in_player_id_value,
					sub_in_name_value,
				])

	def _auto_export_records_csv(self, match_id: str) -> Path:
		script_dir = Path(__file__).parent
		if self.video_path is not None:
			base_name = self.video_path.stem
		else:
			base_name = f"fotmob_{match_id}"
		target_path = script_dir / f"{base_name}_records.csv"
		self._write_records_to_csv(target_path)
		return target_path

	def _sync_fotmob_records(self) -> None:
		for record in self.timeline_records:
			if getattr(record, "player_id", "") == "FOTMOB_AUTO" and hasattr(record, "fotmob_minute"):
				timeline_seconds = float(max(0, record.fotmob_minute) * 60)
				record.time_seconds = self._video_seconds_from_timeline(timeline_seconds)

	def _rebuild_lineups_from_records(self, upto_seconds: float | None = None) -> None:
		global PLAYER_OPTIONS_HOME, PLAYER_OPTIONS_AWAY, BENCH_OPTIONS_HOME, BENCH_OPTIONS_AWAY
		PLAYER_OPTIONS_HOME = list(self.initial_player_options_home)
		BENCH_OPTIONS_HOME = list(self.initial_bench_options_home)
		PLAYER_OPTIONS_AWAY = list(self.initial_player_options_away)
		BENCH_OPTIONS_AWAY = list(self.initial_bench_options_away)

		sorted_records = sorted(enumerate(self.timeline_records), key=lambda item: (item[1].time_seconds, item[0]))
		for _, record in sorted_records:
			if record.action != "교체":
				continue
			if upto_seconds is not None and record.time_seconds > upto_seconds:
				continue
			out_player = format_player_label(record.sub_out_jersey_number, record.sub_out_player_name)
			in_player = format_player_label(record.sub_in_jersey_number, record.sub_in_player_name)
			if (not out_player or not in_player):
				legacy_out = format_player_label(record.jersey_number, record.player_name)
				if legacy_out:
					out_player = legacy_out
				if "->" in record.result:
					in_player = record.result.split("->", 1)[1].strip()
			if not out_player or not in_player:
				continue
			self._apply_substitution_to_lineups(record.team, out_player, in_player)

		if hasattr(self, "player_grid_container"):
			self._rebuild_player_buttons()
			if self.selected_player not in self.current_player_options:
				self.selected_player = None
			self._select_player(self.selected_player)

	def _rebuild_player_buttons(self) -> None:
		if not hasattr(self, "player_grid_container"):
			return
		for child in self.player_grid_container.winfo_children():
			child.destroy()
		self.player_buttons.clear()

		if self.selected_team == "홈":
			current_options = PLAYER_OPTIONS_HOME
			current_bench = BENCH_OPTIONS_HOME
		else:
			current_options = PLAYER_OPTIONS_AWAY
			current_bench = BENCH_OPTIONS_AWAY
		self.current_player_options = current_options
		self.current_bench_options = current_bench

		for index, player_label in enumerate(current_options):
			button = tk.Button(
				self.player_grid_container,
				text=player_label,
				command=lambda value=player_label: self._select_player(value),
				anchor="w",
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=10,
				pady=8,
				width=14,
			)
			button.grid(row=index // 3, column=index % 3, sticky="ew", padx=4, pady=4)
			button.bind("<Button-3>", lambda event, value=player_label: self._on_player_right_click(event, value))
			self.player_buttons[player_label] = button

		# 11명 선수 버튼 뒤에 팀 이름 버튼 추가
		if self.selected_team == "홈":
			team_name = self.home_team_name
		else:
			team_name = self.away_team_name
		team_button_index = len(current_options)
		team_button = tk.Button(
			self.player_grid_container,
			text=team_name,
			command=lambda value=team_name: self._select_player(value),
			anchor="w",
			bg=ACCENT,
			fg="#081017",
			relief="raised",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=10,
			pady=8,
			width=14,
		)
		team_button.grid(row=team_button_index // 3, column=team_button_index % 3, sticky="ew", padx=4, pady=4)
		self.player_buttons[team_name] = team_button

		# 단축키 바인딩: =, Return, Keypad Enter
		def select_team_button_event(_event=None):
			self._select_player(team_name)

		self.bind("=", select_team_button_event)
		self.bind("<Return>", select_team_button_event)
		self.bind("<KP_Enter>", select_team_button_event)
		for column in range(3):
			self.player_grid_container.grid_columnconfigure(column, weight=1)

		if hasattr(self, "custom_player_button"):
			self.custom_player_button.pack(fill="x", pady=(6, 0))

	def _select_team(self, team_label: str) -> None:
		self.selected_team = team_label
		for label, button in self.team_buttons.items():
			if label == team_label:
				button.configure(bg=ACCENT, fg="#081017", relief="sunken")
			else:
				button.configure(bg=CARD_BG, fg=TEXT_MAIN, relief="flat")
		self._rebuild_player_buttons()
		if hasattr(self, "status_var"):
			self.status_var.set(f"팀 선택: {team_label}")

	def _on_player_right_click(self, _event: tk.Event, player_label: str) -> None:
		if self.video_capture is None:
			return
		if not self.current_bench_options:
			messagebox.showinfo("교체", "교체 명단이 없습니다.", parent=self)
			return
		options_text = "\n".join(f"{index + 1}. {name}" for index, name in enumerate(self.current_bench_options))
		selected_index = simpledialog.askinteger(
			"교체",
			f"OUT: {player_label}\nIN 선수를 번호로 선택하세요.\n\n{options_text}",
			parent=self,
			minvalue=1,
			maxvalue=len(self.current_bench_options),
		)
		if selected_index is None:
			return
		in_player = self.current_bench_options[selected_index - 1]
		self._swap_player_with_bench(player_label, in_player)

	def _swap_player_with_bench(self, out_player: str, in_player: str) -> None:
		if out_player not in self.current_player_options:
			return
		if in_player not in self.current_bench_options:
			return

		out_index = self.current_player_options.index(out_player)
		in_index = self.current_bench_options.index(in_player)
		self.current_player_options[out_index] = in_player
		self.current_bench_options[in_index] = out_player

		global PLAYER_OPTIONS_HOME, PLAYER_OPTIONS_AWAY, BENCH_OPTIONS_HOME, BENCH_OPTIONS_AWAY
		if self.selected_team == "홈":
			PLAYER_OPTIONS_HOME = self.current_player_options
			BENCH_OPTIONS_HOME = self.current_bench_options
		else:
			PLAYER_OPTIONS_AWAY = self.current_player_options
			BENCH_OPTIONS_AWAY = self.current_bench_options

		self.selected_player = in_player if self.selected_player == out_player else self.selected_player
		self._rebuild_player_buttons()
		self._select_player(self.selected_player)

		out_jersey, out_name = split_player_label(out_player)
		in_jersey, in_name = split_player_label(in_player)
		self.timeline_records.append(
			TimelineRecord(
				time_seconds=self.current_time_seconds,
				period_label=self._period_label_from_markers(self.current_time_seconds),
				team=self.selected_team,
				jersey_number="",
				player_id="",
				player_name="",
				action="교체",
				result="",
				sub_out_jersey_number=out_jersey,
				sub_out_player_id=self._resolve_player_id(self.selected_team, out_player),
				sub_out_player_name=out_name,
				sub_in_jersey_number=in_jersey,
				sub_in_player_id=self._resolve_player_id(self.selected_team, in_player),
				sub_in_player_name=in_name,
			)
		)
		self.record_counter += 1
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set(f"교체 기록: {self.selected_team} · OUT {out_player} · IN {in_player}")

	def _input_custom_player(self) -> None:
		player_name = simpledialog.askstring("선수 직접 입력", "선수 이름을 입력하세요.", parent=self)
		if player_name is None:
			return
		player_name = player_name.strip()
		if not player_name:
			messagebox.showwarning("선수 선택", "선수 이름을 입력하세요.", parent=self)
			return
		jersey_number = simpledialog.askstring("선수 직접 입력", "등번호(선택)를 입력하세요.", parent=self)
		if jersey_number is None:
			jersey_number = ""
		custom_label = format_player_label(jersey_number.strip(), player_name)
		self._select_player(custom_label)

	def record_current_view(self) -> None:
		if self.video_capture is None:
			return
		self._open_record_dialog(self.current_time_seconds)

	def _select_player(self, player_label: str | None) -> None:
		self.selected_player = player_label
		for label, button in self.player_buttons.items():
			if label == player_label:
				button.configure(bg=ACCENT, fg="#081017", relief="sunken")
			else:
				button.configure(bg=CARD_BG, fg=TEXT_MAIN, relief="flat")
		if player_label is not None:
			self.status_var.set(f"선수 선택: {player_label}")

	def _select_action(self, action_label: str | None) -> None:
		self.selected_action = action_label
		for label, button in self.action_buttons.items():
			if label == action_label:
				button.configure(bg=ACCENT, fg="#081017", relief="sunken")
			else:
				button.configure(bg=CARD_BG, fg=TEXT_MAIN, relief="flat")
		self._rebuild_result_buttons()
		if action_label is not None:
			self.status_var.set(f"액션 선택: {action_label}")

	def _rebuild_result_buttons(self) -> None:
		if self.result_grid is None:
			return
		for child in self.result_grid.winfo_children():
			child.destroy()
		self.result_buttons.clear()

		action_label = self.selected_action
		if not action_label:
			placeholder = tk.Label(
				self.result_grid,
				text="먼저 액션을 선택하세요",
				bg=WINDOW_BG,
				fg=TEXT_MUTED,
				anchor="w",
			)
			placeholder.pack(fill="x", pady=(2, 4))
			if self.result_header_label is not None:
				self.result_header_label.configure(text="결과")
			return

		# 북마크일 때는 '스크린샷', '클립생성' 버튼만 제공
		if action_label == "북마크":
			if self.result_header_label is not None:
				self.result_header_label.configure(text="북마크 옵션")
			screenshot_btn = tk.Button(
				self.result_grid,
				text="스크린샷",
				command=lambda: self._record_action_result("스크린샷"),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=9,
				pady=7,
			)
			screenshot_btn.grid(row=0, column=0, sticky="ew", padx=3, pady=3)
			self.result_buttons["스크린샷"] = screenshot_btn
			clip_btn = tk.Button(
				self.result_grid,
				text="클립생성",
				command=lambda: self._record_action_result("클립생성"),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=9,
				pady=7,
			)
			clip_btn.grid(row=0, column=1, sticky="ew", padx=3, pady=3)
			self.result_buttons["클립생성"] = clip_btn
			for column in range(2):
				self.result_grid.grid_columnconfigure(column, weight=1)
			return

		options = ACTION_RESULT_OPTIONS.get(action_label, [])
		if self.result_header_label is not None:
			self.result_header_label.configure(text=f"결과 ({action_label})")
		for index, result_label in enumerate(options):
			button = tk.Button(
				self.result_grid,
				text=result_label,
				command=lambda value=result_label: self._record_action_result(value),
				bg=CARD_BG,
				fg=TEXT_MAIN,
				relief="flat",
				activebackground=ACCENT_DARK,
				activeforeground=TEXT_MAIN,
				padx=9,
				pady=7,
			)
			button.grid(row=index // 2, column=index % 2, sticky="ew", padx=3, pady=3)
			self.result_buttons[result_label] = button
		for column in range(2):
			self.result_grid.grid_columnconfigure(column, weight=1)

	def _set_quick_record_state(self, state: str) -> None:
		for button in self.team_buttons.values():
			button.configure(state=state)
		for button in self.player_buttons.values():
			button.configure(state=state)
		if hasattr(self, "custom_player_button"):
			self.custom_player_button.configure(state=state)
		for button in self.action_buttons.values():
			button.configure(state=state)
		for button in self.result_buttons.values():
			button.configure(state=state)

	def _record_action_result(self, result_label: str) -> None:
		if self.video_capture is None:
			messagebox.showwarning("행위 기록", "먼저 영상을 불러오세요.", parent=self)
			return
		if not self.selected_player:
			messagebox.showwarning("행위 기록", "먼저 선수를 선택하세요.", parent=self)
			self.status_var.set("먼저 선수를 선택하세요.")
			return
		if not self.selected_action:
			messagebox.showwarning("행위 기록", "먼저 액션을 선택하세요.", parent=self)
			self.status_var.set("먼저 액션을 선택하세요.")
			return

		action_name = self.selected_action
		result_text = result_label

		# --- 1. 북마크이면서 스크린샷/클립생성인 경우 ---
		if action_name == "북마크" and result_label in ("스크린샷", "클립생성"):
			memo = simpledialog.askstring("북마크 메모", "북마크에 남길 메모를 입력하세요.", parent=self)
			if memo is None: return
			memo = memo.strip() or "메모 없음"
			
			if result_label == "스크린샷":
				self._save_screenshot()
			elif result_label == "클립생성":
				self._create_clip()
				
			self.timeline_records.append(
				TimelineRecord(
					time_seconds=self.current_time_seconds,
					period_label=self._period_label_from_markers(self.current_time_seconds),
					team=self.selected_team,
					jersey_number=split_player_label(self.selected_player)[0],
					player_id=self._resolve_player_id(self.selected_team, self.selected_player),
					player_name=split_player_label(self.selected_player)[1],
					action=action_name,
					result=memo,
				)
			)
			self._finish_recording(action_name, memo)
			return # 여기서 종료하여 아래 중복 실행 방지

		# --- 2. 북마크 일반 메모인 경우 ---
		elif action_name == "북마크":
			memo = simpledialog.askstring("북마크", "북마크 메모를 입력하세요.", parent=self)
			if memo is None: return
			memo = memo.strip() or "메모 없음"
			result_text = memo

		# --- 3. 일반 액션 및 북마크 메모 공통 저장 로직 ---
		self.timeline_records.append(
			TimelineRecord(
				time_seconds=self.current_time_seconds,
				period_label=self._period_label_from_markers(self.current_time_seconds),
				team=self.selected_team,
				jersey_number=split_player_label(self.selected_player)[0],
				player_id=self._resolve_player_id(self.selected_team, self.selected_player),
				player_name=split_player_label(self.selected_player)[1],
				action=action_name,
				result=result_text,
			)
		)
		self._finish_recording(action_name, result_text)

	def _finish_recording(self, action_name, result_text):
		"""기록 후 UI 갱신 공통 로직"""
		self.record_counter += 1
		self._refresh_record_tree()
		self._redraw_timeline()
		display_text = action_name if not result_text else f"{action_name} · {result_text}"
		self.status_var.set(f"기록됨: {format_time(self._timeline_seconds(self.current_time_seconds))} · {self.selected_team} · {self.selected_player} · {display_text}")
		self._select_player(None)
		self._select_action(None)

	def _timeline_seconds_from_canvas_x(self, x: float, canvas: tk.Widget | None = None) -> float:
		if self.duration_seconds <= 0:
			return 0.0
		canvas_widget = canvas if canvas is not None and hasattr(canvas, "winfo_width") else self.timeline_canvas
		segment_start = 0.0
		segment_end = self.duration_seconds
		if isinstance(canvas_widget, tk.Canvas):
			start_end = self.timeline_canvas_ranges.get(canvas_widget)
			if start_end is not None:
				segment_start = start_end[0]
				segment_end = start_end[1]
		segment_length = max(0.0, segment_end - segment_start)
		width = max(1, canvas_widget.winfo_width())
		left = 20.0
		right = max(left + 1.0, width - 20.0)
		ratio = clamp((x - left) / (right - left), 0.0, 1.0)
		return segment_start + ratio * segment_length

	def _on_timeline_press(self, event: tk.Event) -> None:
		if self.video_capture is None or self.duration_seconds <= 0:
			return
		self.is_timeline_dragging = True
		self.timeline_drag_was_playing = self.is_playing
		if self.is_playing:
			self.pause_video()
		seconds = self._timeline_seconds_from_canvas_x(float(event.x), getattr(event, "widget", None))
		self.seek_to(seconds)
		self.status_var.set(f"현재 시점 선택: {format_time(self._timeline_seconds(seconds))}")

	def _on_timeline_drag(self, event: tk.Event) -> None:
		if not self.is_timeline_dragging or self.video_capture is None or self.duration_seconds <= 0:
			return
		seconds = self._timeline_seconds_from_canvas_x(float(event.x), getattr(event, "widget", None))
		self.seek_to(seconds)

	def _on_timeline_release(self, event: tk.Event) -> None:
		if not self.is_timeline_dragging or self.video_capture is None:
			return
		self.is_timeline_dragging = False
		seconds = self._timeline_seconds_from_canvas_x(float(event.x), getattr(event, "widget", None))
		self.seek_to(seconds)
		if self.timeline_drag_was_playing:
			self.play_video()
		self.timeline_drag_was_playing = False

	def _on_record_double_click(self, _event: tk.Event) -> None:
		if self.video_capture is None:
			return
		selection = self.record_tree.selection()
		if not selection:
			return
		index = int(selection[0])
		if index < 0 or index >= len(self.timeline_records):
			return
		self.seek_to(self.timeline_records[index].time_seconds)

	def _on_record_delete_key(self, _event: tk.Event) -> str:
		self._delete_selected_record()
		return "break"

	def _delete_selected_record(self) -> None:
		selection = self.record_tree.selection()
		if not selection:
			messagebox.showwarning("기록 삭제", "삭제할 기록을 선택하세요.", parent=self)
			return
		indexes = sorted((int(item) for item in selection), reverse=True)
		for index in indexes:
			if 0 <= index < len(self.timeline_records):
				del self.timeline_records[index]
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set(f"기록 {len(indexes)}개 삭제")

	def _clear_all_records(self) -> None:
		if not self.timeline_records:
			messagebox.showinfo("기록 삭제", "삭제할 기록이 없습니다.", parent=self)
			return
		confirmed = messagebox.askyesno("기록 삭제", "기록을 모두 삭제할까요?", parent=self)
		if not confirmed:
			return
		self.timeline_records.clear()
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set("모든 기록 삭제")

	def _save_records(self) -> None:
		if not self.timeline_records:
			messagebox.showwarning("기록 저장", "저장할 기록이 없습니다.", parent=self)
			return
		default_name = "timeline_records.csv"
		if self.video_path is not None:
			default_name = f"{self.video_path.stem}_records.csv"

		target_path = filedialog.asksaveasfilename(
			title="기록 저장",
			defaultextension=".csv",
			initialfile=default_name,
			filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
		)
		if not target_path:
			return

		try:
			self._write_records_to_csv(Path(target_path))
		except OSError as error:
			messagebox.showerror("기록 저장", f"파일 저장에 실패했습니다.\n{error}", parent=self)
			return

		self.status_var.set(f"기록 저장 완료: {Path(target_path).name}")

	def _build_project_data(self) -> dict:
		return {
			"video_path": str(self.video_path.absolute()) if self.video_path is not None else "",
			"timeline_start_offset_seconds": self.timeline_start_offset_seconds,
			"timeline_adjust_mode": self.timeline_adjust_mode,
			"period_markers": {
				"first_half_start_seconds": self.first_half_start_seconds,
				"first_half_end_seconds": self.first_half_end_seconds,
				"second_half_start_seconds": self.second_half_start_seconds,
				"second_half_end_seconds": self.second_half_end_seconds,
			},
			"team_names": {
				"home": self.home_team_name,
				"away": self.away_team_name,
			},
			"player_id_maps": {
				"home": dict(PLAYER_ID_MAP_HOME),
				"away": dict(PLAYER_ID_MAP_AWAY),
			},
			"lineups": {
				"home": {
					"starting": list(self.initial_player_options_home),
					"bench": list(self.initial_bench_options_home),
				},
				"away": {
					"starting": list(self.initial_player_options_away),
					"bench": list(self.initial_bench_options_away),
				},
			},
			"records": [
				{
					"time_seconds": record.time_seconds,
					"period_label": record.period_label,
					"team": record.team,
					"jersey_number": record.jersey_number,
					"player_id": record.player_id,
					"player_name": record.player_name,
					"action": record.action,
					"result": record.result,
					"sub_out_jersey_number": record.sub_out_jersey_number,
					"sub_out_player_id": record.sub_out_player_id,
					"sub_out_player_name": record.sub_out_player_name,
					"sub_in_jersey_number": record.sub_in_jersey_number,
					"sub_in_player_id": record.sub_in_player_id,
					"sub_in_player_name": record.sub_in_player_name,
				}
				for record in self.timeline_records
			],
		}

	def _has_unsaved_project_changes(self) -> bool:
		if self.video_path is None:
			return False
		current_payload = json.dumps(self._build_project_data(), ensure_ascii=False, sort_keys=True)
		if self.last_saved_project_payload is None:
			return True
		return current_payload != self.last_saved_project_payload


	def _save_project(self) -> None:
		if self.video_path is None:
			messagebox.showwarning("프로젝트 저장", "불러온 영상이 없습니다.", parent=self)
			return

		target_path_obj: Path | None = self.project_file_path
		if target_path_obj is None:
			default_name = f"{self.video_path.stem}_project.json"
			target_path = filedialog.asksaveasfilename(
				title="프로젝트 저장",
				defaultextension=".json",
				initialfile=default_name,
				filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
			)
			if not target_path:
				return
			target_path_obj = Path(target_path)

		try:
			project_data = self._build_project_data()
			with open(target_path_obj, "w", encoding="utf-8") as f:
				json.dump(project_data, f, ensure_ascii=False, indent=2)
		except OSError as error:
			messagebox.showerror("프로젝트 저장", f"파일 저장에 실패했습니다.\n{error}", parent=self)
			return

		self.project_file_path = target_path_obj
		self.last_saved_project_payload = json.dumps(project_data, ensure_ascii=False, sort_keys=True)
		self.status_var.set(f"프로젝트 저장 완료: {target_path_obj.name}")

	def load_project(self) -> None:
		project_path = filedialog.askopenfilename(
			title="프로젝트 불러오기",
			filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
		)
		if not project_path:
			return

		try:
			with open(project_path, "r", encoding="utf-8") as f:
				project_data = json.load(f)
		except (OSError, json.JSONDecodeError) as error:
			messagebox.showerror("프로젝트 불러오기", f"프로젝트를 불러올 수 없습니다.\n{error}", parent=self)
			return

		project_file = Path(project_path)
		project_dir = project_file.parent
		project_stem = project_file.stem  # 예: "Premier League Round 32 아스날 본머스_project"

		# 프로젝트 파일 이름에서 "_project" 접미사가 있다면 제거하여 영상 기본 이름 추출
		if project_stem.endswith("_project"):
			base_video_name = project_stem[:-8] 
		else:
			base_video_name = project_stem

		# 지원하는 영상 확장자 목록을 순회하며 같은 폴더에 영상이 있는지 확인
		found_video_path = None
		for ext in [".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv"]:
			candidate = project_dir / f"{base_video_name}{ext}"
			if candidate.exists():
				found_video_path = candidate
				break

		# 만약 이름이 똑같은 영상 파일을 찾지 못했다면
		if not found_video_path:
			messagebox.showerror(
				"프로젝트 불러오기", 
				f"동일한 폴더에서 프로젝트와 이름이 같은 영상 파일을 찾을 수 없습니다.\n예상 파일명: {base_video_name}.mp4 등", 
				parent=self
			)
			return

		# 찾은 영상으로 로드
		self.load_video(found_video_path)
		self.timeline_start_offset_seconds = float(project_data.get("timeline_start_offset_seconds", 0.0) or 0.0)
		self.timeline_adjust_mode = bool(project_data.get("timeline_adjust_mode", False))
		period_markers = project_data.get("period_markers", {})
		if isinstance(period_markers, dict):
			self.first_half_start_seconds = float(period_markers.get("first_half_start_seconds")) if period_markers.get("first_half_start_seconds") is not None else None
			self.first_half_end_seconds = float(period_markers.get("first_half_end_seconds")) if period_markers.get("first_half_end_seconds") is not None else None
			self.second_half_start_seconds = float(period_markers.get("second_half_start_seconds")) if period_markers.get("second_half_start_seconds") is not None else None
			self.second_half_end_seconds = float(period_markers.get("second_half_end_seconds")) if period_markers.get("second_half_end_seconds") is not None else None
		else:
			self.first_half_start_seconds = None
			self.first_half_end_seconds = None
			self.second_half_start_seconds = None
			self.second_half_end_seconds = None
		if hasattr(self, "timeline_adjust_button"):
			self.timeline_adjust_button.configure(text="타임라인 조정: 전후반" if self.timeline_adjust_mode else "타임라인 조정: 전체")
		team_names = project_data.get("team_names", {})
		if isinstance(team_names, dict):
			self.home_team_name = str(team_names.get("home", "") or "홈팀")
			self.away_team_name = str(team_names.get("away", "") or "어웨이팀")
		else:
			self.home_team_name = "홈팀"
			self.away_team_name = "어웨이팀"
		player_id_maps = project_data.get("player_id_maps", {})
		if isinstance(player_id_maps, dict):
			global PLAYER_ID_MAP_HOME, PLAYER_ID_MAP_AWAY
			PLAYER_ID_MAP_HOME = dict(player_id_maps.get("home", {})) if isinstance(player_id_maps.get("home", {}), dict) else {}
			PLAYER_ID_MAP_AWAY = dict(player_id_maps.get("away", {})) if isinstance(player_id_maps.get("away", {}), dict) else {}
			self.initial_player_id_map_home = dict(PLAYER_ID_MAP_HOME)
			self.initial_player_id_map_away = dict(PLAYER_ID_MAP_AWAY)
		lineups = project_data.get("lineups", {})
		if isinstance(lineups, dict):
			home_lineup = lineups.get("home", {}) if isinstance(lineups.get("home", {}), dict) else {}
			away_lineup = lineups.get("away", {}) if isinstance(lineups.get("away", {}), dict) else {}

			home_starting = home_lineup.get("starting", [])
			home_bench = home_lineup.get("bench", [])
			away_starting = away_lineup.get("starting", [])
			away_bench = away_lineup.get("bench", [])

			if isinstance(home_starting, list):
				self.initial_player_options_home = [str(item).strip() for item in home_starting if str(item).strip()]
			if isinstance(home_bench, list):
				self.initial_bench_options_home = [str(item).strip() for item in home_bench if str(item).strip()]
			if isinstance(away_starting, list):
				self.initial_player_options_away = [str(item).strip() for item in away_starting if str(item).strip()]
			if isinstance(away_bench, list):
				self.initial_bench_options_away = [str(item).strip() for item in away_bench if str(item).strip()]
		records_data = project_data.get("records", [])
		self.timeline_records.clear()
		for record_dict in records_data:
			action_value = record_dict.get("action", "")
			result_value = record_dict.get("result", "")
			sub_out_jersey_value = record_dict.get("sub_out_jersey_number", "")
			sub_out_name_value = record_dict.get("sub_out_player_name", "")
			sub_in_jersey_value = record_dict.get("sub_in_jersey_number", "")
			sub_in_name_value = record_dict.get("sub_in_player_name", "")
			legacy_sub_out = record_dict.get("sub_out_player", "")
			legacy_sub_in = record_dict.get("sub_in_player", "")
			if not sub_out_name_value and legacy_sub_out:
				sub_out_jersey_value, sub_out_name_value = split_player_label(legacy_sub_out)
			if not sub_in_name_value and legacy_sub_in:
				sub_in_jersey_value, sub_in_name_value = split_player_label(legacy_sub_in)
			if action_value == "교체" and (not sub_out_name_value or not sub_in_name_value) and "->" in result_value:
				left, right = result_value.split("->", 1)
				sub_out_jersey_value, sub_out_name_value = split_player_label(left.strip())
				sub_in_jersey_value, sub_in_name_value = split_player_label(right.strip())
				result_value = ""
			# ...
			rec = TimelineRecord(
				time_seconds=record_dict.get("time_seconds", 0),
				period_label=record_dict.get("period_label", ""),
				team=record_dict.get("team", "홈"),
				jersey_number=record_dict.get("jersey_number", ""),
				player_id=record_dict.get("player_id", ""),
				player_name=record_dict.get("player_name", ""),
				action=action_value,
				result=result_value,
				sub_out_jersey_number=sub_out_jersey_value,
				sub_out_player_id=record_dict.get("sub_out_player_id", ""),
				sub_out_player_name=sub_out_name_value,
				sub_in_jersey_number=sub_in_jersey_value,
				sub_in_player_id=record_dict.get("sub_in_player_id", ""),
				sub_in_player_name=sub_in_name_value,
			)
			# 복원 시 당시 기준 분(minute)을 살려둡니다.
			if rec.player_id == "FOTMOB_AUTO":
				rec.fotmob_minute = int(self._timeline_seconds(rec.time_seconds) // 60)
			
			self.timeline_records.append(rec)
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._update_time_label()
		self._refresh_record_tree()
		self._redraw_timeline()
		self.project_file_path = Path(project_path)
		self.last_saved_project_payload = json.dumps(self._build_project_data(), ensure_ascii=False, sort_keys=True)
		self.status_var.set(f"프로젝트 불러오기 완료: {Path(project_path).name}")


	def _refresh_record_tree(self) -> None:
		if not hasattr(self, "record_tree"):
			return
		for item in self.record_tree.get_children():
			self.record_tree.delete(item)
		for index, record in enumerate(self.timeline_records):
			display_action = record.action if not record.result else f"{record.action} · {record.result}"
			player_text = format_player_label(record.jersey_number, record.player_name)
			sub_out_no = record.sub_out_jersey_number
			sub_out_name = record.sub_out_player_name
			sub_in_no = record.sub_in_jersey_number
			sub_in_name = record.sub_in_player_name
			if record.action == "교체" and (not sub_out_name or not sub_in_name) and "->" in record.result:
				left, right = record.result.split("->", 1)
				sub_out_no, sub_out_name = split_player_label(left.strip())
				sub_in_no, sub_in_name = split_player_label(right.strip())
			if record.action == "교체":
				display_action = "교체"
				if sub_out_name and sub_in_name:
					player_text = f"{sub_out_name}->{sub_in_name}"
			self.record_tree.insert(
				"",
				0,
				iid=str(index),
				values=(format_time(self._timeline_seconds(record.time_seconds)), record.team, player_text, display_action),
			)

	def _redraw_timeline(self) -> None:
		if not getattr(self, "timeline_canvases", None):
			return
		self.timeline_canvas_ranges = self._resolve_timeline_ranges()
		marker_times = self._get_marker_times()
		for canvas in self.timeline_canvases:
			if not canvas.winfo_exists():
				continue
			width = max(1, canvas.winfo_width())
			height = max(1, canvas.winfo_height())
			segment_start, segment_end, timeline_label = self.timeline_canvas_ranges.get(
				canvas,
				(0.0, max(0.0, self.duration_seconds), "전체 타임라인"),
			)
			segment_length = max(0.0, segment_end - segment_start)
			canvas.delete("all")
			canvas.create_rectangle(0, 0, width, height, fill=CARD_BG, outline=CARD_BG)
			header_y = 14
			canvas.create_text(20, header_y, text=f"{timeline_label} 드래그로 이동", anchor="w", fill=TEXT_MAIN)
			canvas.create_text(width - 20, header_y, text=f"현재 {format_time(self._timeline_seconds(self.current_time_seconds))}", anchor="e", fill=TEXT_MUTED, tags="cursor")
			bar_y = height - 26
			sub_label_y = max(header_y + 18, bar_y - 22)
			canvas.create_line(20, bar_y, width - 20, bar_y, fill="#314452", width=6)
			if self.duration_seconds > 0 and segment_length > 0:
				for index in range(7):
					tick_seconds = segment_start + (segment_length * index) / 6
					tick_x = 20 + (width - 40) * (index / 6)
					canvas.create_line(tick_x, bar_y + 6, tick_x, bar_y + 11, fill="#5a7182", width=1)
					canvas.create_text(
						tick_x,
						bar_y + 15,
						text=format_time(self._timeline_seconds(tick_seconds)),
						fill=TEXT_MUTED,
						font=("Segoe UI", 8),
					)

				if self.current_time_seconds <= segment_start:
					current_ratio = 0.0
				elif self.current_time_seconds >= segment_end:
					current_ratio = 1.0
				else:
					current_ratio = (self.current_time_seconds - segment_start) / segment_length
				current_x = 20 + (width - 40) * current_ratio
				canvas.create_line(20, bar_y, current_x, bar_y, fill=ACCENT, width=6, tags="cursor")
				canvas.create_oval(current_x - 7, bar_y - 7, current_x + 7, bar_y + 7, fill=ACCENT, outline="", tags="cursor")

				for marker_label, marker_seconds, marker_color in marker_times:
					if marker_seconds < segment_start or marker_seconds > segment_end:
						continue
					ratio = (marker_seconds - segment_start) / segment_length
					x = 20 + (width - 40) * ratio
					marker_label_y = header_y + 24
					canvas.create_line(x, marker_label_y + 4, x, bar_y - 10, fill=marker_color, width=1)
					canvas.create_text(x, marker_label_y, text=marker_label, fill=marker_color, font=("Segoe UI", 8, "bold"), anchor="s")

				for record in self.timeline_records:
					if record.action == "교체":
						continue
					if record.time_seconds < segment_start or record.time_seconds > segment_end:
						continue
					ratio = (record.time_seconds - segment_start) / segment_length
					x = 20 + (width - 40) * ratio
					marker_color = "#4da3ff" if record.team == "홈" else "#ff8c69"
					canvas.create_line(x, bar_y - 18, x, bar_y - 2, fill=marker_color, width=2)
					canvas.create_oval(x - 4, bar_y - 26, x + 4, bar_y - 18, fill=marker_color, outline="")
			else:
				canvas.create_text(width / 2, bar_y, text="영상이 없어서 타임라인을 표시할 수 없습니다", fill=TEXT_MUTED)

	def _update_timeline_cursor(self) -> None:
		"""Lightweight update used during playback: only redraws the three cursor-tagged items
		(progress fill, cursor dot, current-time text) without touching static content."""
		if not getattr(self, "timeline_canvases", None):
			return
		for canvas in self.timeline_canvases:
			if not canvas.winfo_exists():
				continue
			width = max(1, canvas.winfo_width())
			height = max(1, canvas.winfo_height())
			header_y = 14
			bar_y = height - 26

			segment_start, segment_end, _ = self.timeline_canvas_ranges.get(
				canvas, (0.0, max(0.0, self.duration_seconds), "")
			)
			segment_length = max(0.0, segment_end - segment_start)

			canvas.delete("cursor")
			canvas.create_text(
				width - 20, header_y,
				text=f"현재 {format_time(self._timeline_seconds(self.current_time_seconds))}",
				anchor="e", fill=TEXT_MUTED, tags="cursor",
			)
			if self.duration_seconds <= 0 or segment_length <= 0:
				continue

			if self.current_time_seconds <= segment_start:
				current_ratio = 0.0
			elif self.current_time_seconds >= segment_end:
				current_ratio = 1.0
			else:
				current_ratio = (self.current_time_seconds - segment_start) / segment_length
			current_x = 20 + (width - 40) * current_ratio
			canvas.create_line(20, bar_y, current_x, bar_y, fill=ACCENT, width=6, tags="cursor")
			canvas.create_oval(
				current_x - 7, bar_y - 7, current_x + 7, bar_y + 7,
				fill=ACCENT, outline="", tags="cursor",
			)

	def _set_seek_value(self, seconds: float) -> None:
		self._updating_seek = True
		try:
			self.seek_scale.set(seconds)
		finally:
			self._updating_seek = False

	def _update_time_label(self) -> None:
		self.time_label.configure(
			text=f"{format_time(self._timeline_seconds(self.current_time_seconds))} / {format_time(self._timeline_seconds(self.duration_seconds))}"
		)

	def _on_video_panel_resize(self, event: tk.Event) -> None:
		self._video_panel_width = max(1, event.width - 12)
		self._video_panel_height = max(1, event.height - 12)

	def _display_frame(self, frame, *, fast: bool = False) -> None:
		if Image is None or ImageTk is None:
			raise RuntimeError("Pillow(PIL)가 설치되어 있지 않습니다.")

		# Use cached panel size; fall back to winfo only when cache is not yet populated.
		canvas_width = self._video_panel_width or max(1, self.video_panel.winfo_width() - 12)
		canvas_height = self._video_panel_height or max(1, self.video_panel.winfo_height() - 12)
		if canvas_width < 50 or canvas_height < 50:
			canvas_width = 960
			canvas_height = 540

		frame_h, frame_w = frame.shape[:2]
		scale = min(canvas_width / frame_w, canvas_height / frame_h)
		target_w = max(1, int(frame_w * scale))
		target_h = max(1, int(frame_h * scale))

		if target_w != frame_w or target_h != frame_h:
			if fast:
				# INTER_LINEAR gives a clean image at negligible cost vs INTER_NEAREST.
				interpolation = cv2.INTER_LINEAR
			else:
				# INTER_AREA is best for downscaling; INTER_CUBIC is sharper than LINEAR for upscaling.
				interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
			frame = cv2.resize(frame, (target_w, target_h), interpolation=interpolation)

		frame_rgb = frame[:, :, ::-1]  # BGR→RGB view (no extra allocation)
		image = Image.fromarray(frame_rgb)
		photo = ImageTk.PhotoImage(image)
		self.current_frame_photo = photo
		self.video_panel.configure(image=photo, text="")
		self.video_panel.image = photo

	def _show_placeholder(self, message: str) -> None:
		self.current_frame_photo = None
		self.video_panel.configure(image="", text=message)
		self.video_panel.image = None

	def _advance_playback(self) -> None:
		capture = self.video_capture
		if capture is None or not self.is_playing:
			return

		now = time.perf_counter()
		elapsed = now - self.last_tick_time
		self.last_tick_time = now
		self.playback_frame_accumulator += elapsed * self.video_fps
		frames_to_advance = int(self.playback_frame_accumulator)
		if frames_to_advance <= 0:
			return
		self.playback_frame_accumulator -= frames_to_advance

		latest_frame = None
		skipping = frames_to_advance > 1
		fps = self.video_fps
		frame_count = self.video_frame_count
		if frames_to_advance > MAX_DECODE_FRAMES_PER_TICK:
			target_index = self.current_frame_index + frames_to_advance - 1
			if frame_count > 0:
				target_index = min(target_index, frame_count - 1)
			capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, target_index))
			success, frame = capture.read()
			if not success:
				self.pause_video()
				self.current_time_seconds = self.duration_seconds
				self._set_seek_value(self.duration_seconds)
				self._update_time_label()
				return
			latest_frame = frame
			self.current_frame_index = target_index + 1
			self.current_time_seconds = self.current_frame_index / fps if fps > 0 else self.current_time_seconds
		else:
			frame_index = self.current_frame_index
			current_time = self.current_time_seconds
			for _ in range(frames_to_advance):
				success, frame = capture.read()
				if not success:
					self.current_frame_index = frame_index
					self.current_time_seconds = current_time
					self.pause_video()
					self.current_time_seconds = self.duration_seconds
					self._set_seek_value(self.duration_seconds)
					self._update_time_label()
					return
				latest_frame = frame
				frame_index += 1
				current_time = frame_index / fps if fps > 0 else current_time
				if frame_count > 0 and frame_index >= frame_count:
					break
			self.current_frame_index = frame_index
			self.current_time_seconds = current_time

		if latest_frame is not None:
			self._display_frame(latest_frame, fast=skipping)
			# Update seek bar and time label at ~15 fps (every other tick) rather than every frame.
			self._playback_ui_skip_counter += 1
			if self._playback_ui_skip_counter >= 2:
				self._playback_ui_skip_counter = 0
				self._set_seek_value(self.current_time_seconds)
				self._update_time_label()
			# Cursor-only timeline update is cheap; full redraw not needed mid-playback.
			self._update_timeline_cursor()
			if frame_count > 0 and self.current_frame_index >= frame_count:
				self._set_seek_value(self.current_time_seconds)
				self._update_time_label()
				self.pause_video()

	def _tick(self) -> None:
		if self.is_playing and not self.is_scrubbing:
			self._pump_audio_player()
			self._advance_playback()
			# Resync audio every ~130 ticks (~2 s) to correct drift without blocking the render loop.
			self._audio_resync_counter += 1
			if self._audio_resync_counter >= 130:
				self._audio_resync_counter = 0
				self._resync_audio_if_needed()
			# Schedule next tick tightly while playing.
			self.after(15, self._tick)
		else:
			# When paused, keep the ffpyplayer pipeline alive with a single get_frame() call.
			# Without this the pipeline goes cold and set_pause(False) may not restart audio.
			if self.audio_player is not None:
				try:
					self.audio_player.get_frame()
				except Exception:
					pass
			# Slow the tick to reduce CPU usage — especially important in packaged exe.
			self.after(100, self._tick)

	def _on_space_key(self, _event: tk.Event) -> str:
		self.toggle_playback()
		return "break"

	def _on_left_key(self, _event: tk.Event) -> str:
		self.seek_relative(-3.0)
		return "break"

	def _on_right_key(self, _event: tk.Event) -> str:
		self.seek_relative(3.0)
		return "break"

	def _on_close(self) -> None:
		if self._has_unsaved_project_changes():
			answer = messagebox.askyesnocancel("프로젝트 저장", "저장하지 않은 변경 사항이 있습니다. 저장할까요?", parent=self)
			if answer is None:
				return
			if answer:
				self._save_project()
				if self._has_unsaved_project_changes():
					return
		self._release_video()
		self.destroy()


def main() -> None:
	if cv2 is None:
		show_error("영상 재생", "OpenCV(cv2)가 설치되어 있지 않습니다.")
		return
	if Image is None or ImageTk is None:
		show_error("영상 재생", "Pillow(PIL)가 설치되어 있지 않습니다.")
		return
	set_windows_app_user_model_id("football.recording.instant")

	app = VideoPlayerApp()
	app.mainloop()


if __name__ == "__main__":
	main()
