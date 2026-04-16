from __future__ import annotations

import csv
import re
import time
import unicodedata
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import tkinter as tk
from tkinter import ttk
import json
from urllib.parse import parse_qs, urlparse
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


VIDEO_FILETYPES = [
	("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.wmv *.flv"),
	("All files", "*.*"),
]

WINDOW_BG = "#0c1419"
PANEL_BG = "#101920"
CARD_BG = "#16232d"
TEXT_MAIN = "#edf3f7"
TEXT_MUTED = "#93a8b8"
ACCENT = "#1dbf73"
ACCENT_DARK = "#15915a"
MAX_DECODE_FRAMES_PER_TICK = 6

ACTION_RESULT_OPTIONS: dict[str, list[str]] = {
	"패스": ["기가막히는패스", "깔끔한원터치패스", "좋은패스", "패스미스", "좋은전환패스", "전환패스실패", "좋은롱패스", "롱패스실패", "판단미스"],
	"크로스": ["좋은크로스", "똥크로스", "에라이크로스"],
	"골": ["원더골", "헤딩골", "좋은마무리", "그냥골"],
	"슈팅": ["좋은슈팅", "아쉬운마무리"],
	"드리블": ["좋은드리블", "무리한드리블"],
	"터치": ["좋은터치", "아쉬운터치", "실수"],
	"수비": ["좋은인터셉트", "슈퍼태클", "좋은태클"],
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


@dataclass
class TimelineRecord:
	time_seconds: float
	team: str
	jersey_number: str
	player_name: str
	action: str
	result: str = ""
	sub_out_jersey_number: str = ""
	sub_out_player_name: str = ""
	sub_in_jersey_number: str = ""
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

	def apply(self) -> None:
		return None


def clamp(value: float, minimum: float, maximum: float) -> float:
	return max(minimum, min(maximum, value))


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

	parts = text.split(":")
	if len(parts) == 1 and " " in text:
		parts = text.split()
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

	raise ValueError("지원 형식: 70, 70:00, 01:10:00, 70 00, 01 10 00")

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


def _extract_lineups_from_match_html(match_url: str, match_id: str) -> dict:
	html = fetch_text(match_url)
	shirt_number_map = _extract_shirt_number_map_from_html(html)

	lineup_para_match = re.search(r"<p[^>]*>The lineups are:(.*?)</p>", html, re.IGNORECASE | re.DOTALL)
	if not lineup_para_match:
		raise ValueError("경기 페이지에서 선발 명단 섹션을 찾지 못했습니다.")

	lineup_para_html = lineup_para_match.group(1)
	segments = [segment for segment in lineup_para_html.split("<br/>") if segment.strip()]
	parsed_teams: list[tuple[str, list[str]]] = []
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
		raw_starter_names = [_clean_html_text(name) for name in re.findall(r"<a[^>]*>(.*?)</a>", players_html, re.DOTALL)]
		starter_names: list[str] = []
		for player_name in raw_starter_names:
			if not player_name:
				continue
			shirt_number = shirt_number_map.get(_normalize_player_name_for_match(player_name), "")
			starter_names.append(format_player_label(shirt_number, player_name))
		starter_names = _dedupe_keep_order(starter_names)
		if team_name and starter_names:
			parsed_teams.append((team_name, starter_names))

	if len(parsed_teams) < 2:
		raise ValueError("경기 페이지에서 홈/어웨이 선발 명단을 찾지 못했습니다.")

	bench_blocks = re.findall(r"<ul[^>]*BenchContainer[^>]*>(.*?)</ul>", html, re.IGNORECASE | re.DOTALL)
	bench_lists: list[list[str]] = []
	for block in bench_blocks:
		players: list[str] = []
		pairs = re.findall(
			r"<span[^>]*Shirt[^>]*>(.*?)</span>.*?<span[^>]*PlayerName[^>]*>(.*?)</span>",
			block,
			re.IGNORECASE | re.DOTALL,
		)
		if pairs:
			for shirt_text, player_text in pairs:
				shirt_number = re.sub(r"\D+", "", _clean_html_text(shirt_text))
				player_name = _clean_html_text(player_text)
				if player_name:
					players.append(format_player_label(shirt_number, player_name))
		else:
			for player_text in re.findall(r"<span[^>]*PlayerName[^>]*>(.*?)</span>", block, re.IGNORECASE | re.DOTALL):
				player_name = _clean_html_text(player_text)
				if player_name:
					shirt_number = shirt_number_map.get(_normalize_player_name_for_match(player_name), "")
					players.append(format_player_label(shirt_number, player_name))
		players = _dedupe_keep_order(players)
		if len(players) >= 3:
			bench_lists.append(players)

	home_team_name, home_starters = parsed_teams[0]
	away_team_name, away_starters = parsed_teams[1]
	home_bench = bench_lists[0] if len(bench_lists) >= 1 else []
	away_bench = bench_lists[1] if len(bench_lists) >= 2 else []

	return {
		"home_team_name": home_team_name,
		"away_team_name": away_team_name,
		"home_starting": home_starters,
		"home_bench": home_bench,
		"away_starting": away_starters,
		"away_bench": away_bench,
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

	# Parse each match-event block first, then extract SubIn/SubOut/time inside the same block.
	# This avoids missing substitutions due to fixed regex distance limits.
	event_block_pattern = re.compile(
		r"MatchEventItemWrapper[^>]*>(.*?)(?=MatchEventItemWrapper|$)",
		re.IGNORECASE | re.DOTALL,
	)

	home_label_map = _build_name_to_label_map(home_starting + home_bench)
	away_label_map = _build_name_to_label_map(away_starting + away_bench)
	home_pool = _build_name_set_from_labels(home_starting + home_bench)
	away_pool = _build_name_set_from_labels(away_starting + away_bench)
	home_subs: list[dict] = []
	away_subs: list[dict] = []

	event_rows: list[tuple[str, str, str]] = []
	for event_block in event_block_pattern.findall(html):
		in_names = re.findall(r"<span[^>]*class=\"[^\"]*SubIn[^\"]*\"[^>]*>([^<]+)</span>", event_block, re.IGNORECASE)
		out_names = re.findall(r"<span[^>]*class=\"[^\"]*SubOut[^\"]*\"[^>]*>([^<]+)</span>", event_block, re.IGNORECASE)
		if not in_names or not out_names:
			continue

		minute_text = ""
		for candidate in re.findall(r"(?:EventTimeMain|SubText)[^>]*>([^<]+)</span>", event_block, re.IGNORECASE):
			if _parse_fotmob_minute_text(candidate) is not None:
				minute_text = candidate
				break
		if not minute_text:
			continue

		pair_count = min(len(in_names), len(out_names))
		for index in range(pair_count):
			event_rows.append((minute_text, in_names[index], out_names[index]))

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

		event_key = (minute, out_norm, in_norm)
		if event_key in seen_events:
			continue
		seen_events.add(event_key)
		if out_norm in home_pool or in_norm in home_pool:
			out_label = home_label_map.get(out_norm, out_name)
			in_label = home_label_map.get(in_norm, in_name)
			sub_record = {
				"minute": minute,
				"out_player": out_label,
				"in_player": in_label,
			}
			home_subs.append(sub_record)
		elif out_norm in away_pool or in_norm in away_pool:
			out_label = away_label_map.get(out_norm, out_name)
			in_label = away_label_map.get(in_norm, in_name)
			sub_record = {
				"minute": minute,
				"out_player": out_label,
				"in_player": in_label,
			}
			away_subs.append(sub_record)

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
			key = (
				minute,
				_normalize_player_name_for_match(out_player),
				_normalize_player_name_for_match(in_player),
			)
			existing = merged_by_key.get(key)
			if existing is None:
				merged_by_key[key] = {
					"minute": minute,
					"out_player": out_player,
					"in_player": in_player,
				}
				continue

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
	for key in ("shirtNo", "shirtNumber", "number", "jerseyNumber", "jerseyNo", "shirt"):
		value = player.get(key)
		if isinstance(value, int):
			return str(value)
		if isinstance(value, str) and value.strip().isdigit():
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


def _extract_team_lineup(team_data: dict) -> tuple[list[str], list[str]]:
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

	starters = _extract_players_from_list(starters_raw or [])
	bench = _extract_players_from_list(bench_raw or [])

	if not starters and isinstance(team_data.get("lineup"), list):
		starters = _extract_players_from_list(team_data.get("lineup", []))

	return starters, bench


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
			player_id = item.get("id")
			if isinstance(player_id, int):
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
	sub_in_by_minute: dict[int, list[str]] = {}
	sub_out_by_minute: dict[int, list[str]] = {}

	for player in players:
		label = _normalize_player_label(player)
		if not label:
			continue
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
			event_type = str(event.get("type", "")).strip().lower()
			if "subin" in event_type:
				sub_in_by_minute.setdefault(minute, []).append(label)
			elif "subout" in event_type:
				sub_out_by_minute.setdefault(minute, []).append(label)

	substitutions: list[dict] = []
	all_minutes = sorted(set(sub_in_by_minute.keys()) | set(sub_out_by_minute.keys()))
	for minute in all_minutes:
		in_list = sub_in_by_minute.get(minute, [])
		out_list = sub_out_by_minute.get(minute, [])
		pair_count = min(len(in_list), len(out_list))
		for index in range(pair_count):
			substitutions.append(
				{
					"minute": minute,
					"out_player": out_list[index],
					"in_player": in_list[index],
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

	home_starters, home_bench = _extract_team_lineup(home_team_data)
	away_starters, away_bench = _extract_team_lineup(away_team_data)

	if not home_starters or not away_starters:
		fallback_url = match_url.strip() or f"https://www.fotmob.com/match/{match_id}"
		return _extract_lineups_from_match_html(fallback_url, match_id)

	home_substitutions = _extract_substitutions_from_team_data(home_team_data)
	away_substitutions = _extract_substitutions_from_team_data(away_team_data)
	if match_url.strip():
		try:
			html_home_substitutions, html_away_substitutions = _extract_substitutions_from_match_html(
				match_url.strip(),
				home_starters,
				home_bench,
				away_starters,
				away_bench,
			)
			home_substitutions = _merge_substitution_lists(home_substitutions, html_home_substitutions)
			away_substitutions = _merge_substitution_lists(away_substitutions, html_away_substitutions)
		except Exception:
			pass

	return {
		"home_team_name": _extract_team_name(data, "home", "홈팀"),
		"away_team_name": _extract_team_name(data, "away", "어웨이팀"),
		"home_starting": home_starters,
		"home_bench": home_bench,
		"away_starting": away_starters,
		"away_bench": away_bench,
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
	def __init__(self) -> None:
		super().__init__()
		self.title("Video Player")
		self.configure(bg=WINDOW_BG)
		self.geometry("1100x760")
		self.minsize(820, 560)

		self.video_capture = None
		self.video_path: Path | None = None
		self.video_fps = 30.0
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
		self.current_player_options: list[str] = []
		self.current_bench_options: list[str] = []
		self.initial_player_options_home: list[str] = []
		self.initial_player_options_away: list[str] = []
		self.initial_bench_options_home: list[str] = []
		self.initial_bench_options_away: list[str] = []

		self._build_styles()
		self._build_layout()
		self._bind_shortcuts()
		self.protocol("WM_DELETE_WINDOW", self._on_close)
		self.after(15, self._tick)

	def _bind_shortcuts(self) -> None:
		self.bind("<space>", self._on_space_key)
		self.bind("<Left>", self._on_left_key)
		self.bind("<Right>", self._on_right_key)
		self.focus_set()

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
			text="타임라인 시작 시각",
			command=self._set_timeline_start_offset,
			bg=CARD_BG,
			fg=TEXT_MAIN,
			relief="flat",
			activebackground=ACCENT_DARK,
			activeforeground=TEXT_MAIN,
			padx=14,
			pady=8,
		)
		self.timeline_offset_button.pack(side="left", padx=(0, 8))

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
		seek_row.columnconfigure(0, weight=1)

		self.seek_scale = ttk.Scale(
			seek_row,
			from_=0.0,
			to=1.0,
			orient="horizontal",
			command=self._on_seek_change,
			style="Timeline.Horizontal.TScale",
		)
		self.seek_scale.grid(row=0, column=0, sticky="ew")
		self.seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
		self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

		content_row = ttk.Frame(self, style="Panel.TFrame")
		content_row.pack(fill="both", expand=True, padx=12, pady=(0, 8))
		content_row.columnconfigure(0, weight=1)
		content_row.rowconfigure(0, weight=1)

		left_content = ttk.Frame(content_row, style="Panel.TFrame")
		left_content.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

		self.video_panel = tk.Label(
			left_content,
			bg="black",
			fg=TEXT_MAIN,
			text="영상이 선택되면 여기에 표시됩니다",
			font=("Segoe UI", 16, "bold"),
			compound="center",
		)
		self.video_panel.pack(fill="both", expand=True, pady=(0, 10))

		self.timeline_canvas = tk.Canvas(left_content, bg=CARD_BG, highlightthickness=0, height=92)
		self.timeline_canvas.pack(fill="x", pady=(0, 10))
		self.timeline_canvas.bind("<Configure>", lambda _event: self._redraw_timeline())
		self.timeline_canvas.bind("<ButtonPress-1>", self._on_timeline_press)
		self.timeline_canvas.bind("<B1-Motion>", self._on_timeline_drag)
		self.timeline_canvas.bind("<ButtonRelease-1>", self._on_timeline_release)

		self._build_record_list_section(left_content)

		self.sidebar_frame = ttk.Frame(content_row, style="Panel.TFrame", width=390)
		self.sidebar_frame.grid(row=0, column=1, sticky="nsew")
		self.sidebar_frame.pack_propagate(False)
		self._build_quick_record_panel(self.sidebar_frame)

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
		return max(0.0, video_seconds + self.timeline_start_offset_seconds)

	def _video_seconds_from_timeline(self, timeline_seconds: float) -> float:
		return max(0.0, timeline_seconds - self.timeline_start_offset_seconds)

	def _set_timeline_start_offset(self) -> None:
		current_text = format_time(self.timeline_start_offset_seconds)
		raw_value = simpledialog.askstring(
			"타임라인 시작 시각",
			"경기 타임라인 시작 시각을 입력하세요.\n예: 70 또는 70:00 또는 01:10:00 또는 70 00",
			parent=self,
			initialvalue=current_text,
		)
		if raw_value is None:
			return

		try:
			offset_seconds = parse_timeline_offset_input(raw_value)
		except ValueError as error:
			messagebox.showwarning("타임라인 시작 시각", str(error), parent=self)
			return

		self.timeline_start_offset_seconds = offset_seconds
		self._update_time_label()
		self._refresh_record_tree()
		self._redraw_timeline()
		self.status_var.set(f"타임라인 시작 시각 설정: {format_time(self.timeline_start_offset_seconds)}")

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
		self.record_tree = ttk.Treeview(parent, columns=columns, show="headings", height=4)
		self.record_tree.heading("time", text="시각")
		self.record_tree.heading("team", text="팀")
		self.record_tree.heading("player", text="선수")
		self.record_tree.heading("action", text="행위")
		self.record_tree.column("time", width=60, anchor="center")
		self.record_tree.column("team", width=50, anchor="center")
		self.record_tree.column("player", width=230, anchor="w")
		self.record_tree.column("action", width=120, anchor="w")
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

	def open_video_file(self) -> None:
		if cv2 is None:
			show_error("영상 재생", "OpenCV(cv2)가 설치되어 있지 않습니다.")
			return

		selected_path = filedialog.askopenfilename(
			title="재생할 영상 선택",
			initialdir=str(Path.cwd()),
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
		self.status_var.set(f"불러온 파일: {video_path.name}")
		self._redraw_timeline()
		self._refresh_record_tree()

		first_frame_ok, first_frame = capture.read()
		if first_frame_ok:
			self.current_frame_index = 1
			self.current_time_seconds = 0.0
			self._display_frame(first_frame)
		else:
			self._show_placeholder("프레임을 읽을 수 없습니다")

	def _release_video(self) -> None:
		if self.video_capture is not None:
			self.video_capture.release()
		self.video_capture = None
		self.video_path = None
		self.video_fps = 30.0
		self.video_frame_count = 0
		self.duration_seconds = 0.0
		self.current_frame_index = 0
		self.current_time_seconds = 0.0
		self.playback_frame_accumulator = 0.0
		self.is_playing = False
		self.is_scrubbing = False
		self.scrub_was_playing = False
		self.current_frame_photo = None
		self.play_button.configure(text="재생")
		if hasattr(self, "record_button"):
			self.record_button.configure(state="disabled")
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
		self.is_playing = True
		self.last_tick_time = time.perf_counter()
		self.playback_frame_accumulator = 0.0
		self.play_button.configure(text="일시정지")
		if self.video_path is not None:
			self.status_var.set(f"재생 중: {self.video_path.name}")

	def pause_video(self) -> None:
		if self.video_capture is None:
			return
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
		self.timeline_records.append(
			TimelineRecord(
				time_seconds=seconds,
				team=dialog.team_name,
				jersey_number=dialog.jersey_number,
				player_name=dialog.player_name,
				action=dialog.action_name,
				result="",
			)
		)
		self.record_counter += 1
		self._refresh_record_tree()
		self._redraw_timeline()
		player_text = format_player_label(dialog.jersey_number, dialog.player_name)
		self.status_var.set(f"현재 시점 기록: {format_time(self._timeline_seconds(seconds))} · {dialog.team_name} · {player_text} · {dialog.action_name}")

	def _load_player_files(self) -> None:
		script_dir = Path(__file__).parent
		home_file = script_dir / "players_home.txt"
		away_file = script_dir / "players_away.txt"
		global PLAYER_OPTIONS_HOME, PLAYER_OPTIONS_AWAY, BENCH_OPTIONS_HOME, BENCH_OPTIONS_AWAY
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

		self._load_player_files()
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
		out_index = _find_player_label_index(starting, out_player)
		in_index = _find_player_label_index(bench, in_player)
		if out_index < 0 or in_index < 0:
			return
		starting[out_index] = in_player
		bench[in_index] = out_player

	def _append_fotmob_substitution_records(self, team: str, substitutions: list[dict]) -> int:
		added_count = 0
		for substitution in substitutions:
			if not isinstance(substitution, dict):
				continue
			out_player = str(substitution.get("out_player", "")).strip()
			in_player = str(substitution.get("in_player", "")).strip()
			minute = _to_int_minutes(substitution.get("minute"))
			if not out_player or not in_player or minute is None:
				continue

			timeline_seconds = float(max(0, minute) * 60)
			# Keep all FotMob substitutions in records even if they are before timeline offset.
			seconds = timeline_seconds - self.timeline_start_offset_seconds
			out_jersey, out_name = split_player_label(out_player)
			in_jersey, in_name = split_player_label(in_player)
			if not out_name or not in_name:
				continue

			exists = any(
				record.action == "교체"
				and record.team == team
				and abs(record.time_seconds - seconds) < 0.5
				and record.sub_out_player_name == out_name
				and record.sub_in_player_name == in_name
				for record in self.timeline_records
			)
			if exists:
				continue

			self.timeline_records.append(
				TimelineRecord(
					time_seconds=seconds,
					team=team,
					jersey_number="",
					player_name=out_name,
					action="교체",
					result="",
					sub_out_jersey_number=out_jersey,
					sub_out_player_name=out_name,
					sub_in_jersey_number=in_jersey,
					sub_in_player_name=in_name,
				)
			)
			added_count += 1

		return added_count

	def _write_records_to_csv(self, target_path: Path) -> None:
		with open(target_path, "w", newline="", encoding="utf-8-sig") as csv_file:
			writer = csv.writer(csv_file)
			writer.writerow([
				"time_seconds",
				"video_time_seconds",
				"time_text",
				"team",
				"jersey_number",
				"player_name",
				"action",
				"result",
				"sub_out_jersey_number",
				"sub_out_player_name",
				"sub_in_jersey_number",
				"sub_in_player_name",
			])
			records = list(enumerate(self.timeline_records))
			records.sort(key=lambda item: (item[1].time_seconds, item[0]))
			for _, record in records:
				action_value = record.action
				result_value = record.result
				jersey_value = record.jersey_number
				player_name_value = record.player_name
				sub_out_jersey_value = record.sub_out_jersey_number
				sub_out_name_value = record.sub_out_player_name
				sub_in_jersey_value = record.sub_in_jersey_number
				sub_in_name_value = record.sub_in_player_name
				team_value = record.team or "우리팀"
				# Legacy data safety: split combined text like "액션 · 결과" if result is empty.
				if not result_value and " · " in action_value:
					action_value, result_value = action_value.split(" · ", 1)
				if action_value == "교체" and (not sub_out_name_value or not sub_in_name_value) and "->" in result_value:
					left, right = result_value.split("->", 1)
					sub_out_jersey_value, sub_out_name_value = split_player_label(left.strip())
					sub_in_jersey_value, sub_in_name_value = split_player_label(right.strip())
					result_value = ""
				if action_value == "교체":
					jersey_value = ""
				if action_value != "교체" and not jersey_value and player_name_value:
					legacy_jersey, legacy_name = split_player_label(player_name_value)
					if legacy_jersey:
						jersey_value = legacy_jersey
						player_name_value = legacy_name
				writer.writerow([
					round(self._timeline_seconds(record.time_seconds), 3),
					round(record.time_seconds, 3),
					format_time_for_csv(self._timeline_seconds(record.time_seconds)),
					team_value,
					jersey_value,
					player_name_value,
					action_value,
					result_value,
					sub_out_jersey_value,
					sub_out_name_value,
					sub_in_jersey_value,
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
				team=self.selected_team,
				jersey_number="",
				player_name=out_name,
				action="교체",
				result="",
				sub_out_jersey_number=out_jersey,
				sub_out_player_name=out_name,
				sub_in_jersey_number=in_jersey,
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
		if self.selected_action == "북마크":
			memo = simpledialog.askstring("북마크", "북마크 메모를 입력하세요.", parent=self)
			if memo is None:
				return
			memo = memo.strip()
			if not memo:
				memo = "메모 없음"
			result_text = memo

		self.timeline_records.append(
			TimelineRecord(
				time_seconds=self.current_time_seconds,
				team=self.selected_team,
				jersey_number=split_player_label(self.selected_player)[0],
				player_name=split_player_label(self.selected_player)[1],
				action=action_name,
				result=result_text,
			)
		)
		self.record_counter += 1
		self._refresh_record_tree()
		self._redraw_timeline()
		display_text = action_name if not result_text else f"{action_name} · {result_text}"
		self.status_var.set(f"기록됨: {format_time(self._timeline_seconds(self.current_time_seconds))} · {self.selected_team} · {self.selected_player} · {display_text}")

	def _timeline_seconds_from_canvas_x(self, x: float) -> float:
		if self.duration_seconds <= 0:
			return 0.0
		width = max(1, self.timeline_canvas.winfo_width())
		left = 20.0
		right = max(left + 1.0, width - 20.0)
		ratio = clamp((x - left) / (right - left), 0.0, 1.0)
		return ratio * self.duration_seconds

	def _on_timeline_press(self, event: tk.Event) -> None:
		if self.video_capture is None or self.duration_seconds <= 0:
			return
		self.is_timeline_dragging = True
		self.timeline_drag_was_playing = self.is_playing
		if self.is_playing:
			self.pause_video()
		seconds = self._timeline_seconds_from_canvas_x(float(event.x))
		self.seek_to(seconds)
		self.status_var.set(f"현재 시점 선택: {format_time(self._timeline_seconds(seconds))}")

	def _on_timeline_drag(self, event: tk.Event) -> None:
		if not self.is_timeline_dragging or self.video_capture is None or self.duration_seconds <= 0:
			return
		seconds = self._timeline_seconds_from_canvas_x(float(event.x))
		self.seek_to(seconds)

	def _on_timeline_release(self, event: tk.Event) -> None:
		if not self.is_timeline_dragging or self.video_capture is None:
			return
		self.is_timeline_dragging = False
		seconds = self._timeline_seconds_from_canvas_x(float(event.x))
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


	def _save_project(self) -> None:
		if self.video_path is None:
			messagebox.showwarning("프로젝트 저장", "불러온 영상이 없습니다.", parent=self)
			return

		default_name = f"{self.video_path.stem}_project.json"
		target_path = filedialog.asksaveasfilename(
			title="프로젝트 저장",
			defaultextension=".json",
			initialfile=default_name,
			filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
		)
		if not target_path:
			return

		try:
			project_data = {
				"video_path": str(self.video_path.absolute()),
				"timeline_start_offset_seconds": self.timeline_start_offset_seconds,
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
						"team": record.team,
						"jersey_number": record.jersey_number,
						"player_name": record.player_name,
						"action": record.action,
						"result": record.result,
						"sub_out_jersey_number": record.sub_out_jersey_number,
						"sub_out_player_name": record.sub_out_player_name,
						"sub_in_jersey_number": record.sub_in_jersey_number,
						"sub_in_player_name": record.sub_in_player_name,
					}
					for record in self.timeline_records
				],
			}
			with open(target_path, "w", encoding="utf-8") as f:
				json.dump(project_data, f, ensure_ascii=False, indent=2)
		except OSError as error:
			messagebox.showerror("프로젝트 저장", f"파일 저장에 실패했습니다.\n{error}", parent=self)
			return

		self.status_var.set(f"프로젝트 저장 완료: {Path(target_path).name}")

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

		video_path_str = project_data.get("video_path")
		if not video_path_str:
			messagebox.showerror("프로젝트 불러오기", "프로젝트에 영상 경로가 없습니다.", parent=self)
			return

		video_path = Path(video_path_str)
		if not video_path.exists():
			messagebox.showerror("프로젝트 불러오기", f"영상 파일을 찾을 수 없습니다.\n{video_path}", parent=self)
			return

		self.load_video(video_path)
		self.timeline_start_offset_seconds = float(project_data.get("timeline_start_offset_seconds", 0.0) or 0.0)
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
			self.timeline_records.append(
				TimelineRecord(
					time_seconds=record_dict.get("time_seconds", 0),
					team=record_dict.get("team", "홈"),
					jersey_number=record_dict.get("jersey_number", ""),
					player_name=record_dict.get("player_name", ""),
					action=action_value,
					result=result_value,
					sub_out_jersey_number=sub_out_jersey_value,
					sub_out_player_name=sub_out_name_value,
					sub_in_jersey_number=sub_in_jersey_value,
					sub_in_player_name=sub_in_name_value,
				)
			)
		self._rebuild_lineups_from_records(self.current_time_seconds)
		self._update_time_label()
		self._refresh_record_tree()
		self._redraw_timeline()
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
		if not hasattr(self, "timeline_canvas"):
			return
		canvas = self.timeline_canvas
		if not canvas.winfo_exists():
			return
		width = max(1, canvas.winfo_width())
		height = max(1, canvas.winfo_height())
		canvas.delete("all")
		canvas.create_rectangle(0, 0, width, height, fill=CARD_BG, outline=CARD_BG)
		canvas.create_text(20, 14, text="타임라인 드래그로 이동", anchor="w", fill=TEXT_MAIN)
		canvas.create_text(width - 20, 14, text=f"현재 {format_time(self._timeline_seconds(self.current_time_seconds))}", anchor="e", fill=TEXT_MUTED)
		bar_y = height - 26
		canvas.create_line(20, bar_y, width - 20, bar_y, fill="#314452", width=6)
		if self.duration_seconds > 0:
			for index in range(7):
				tick_seconds = (self.duration_seconds * index) / 6
				tick_x = 20 + (width - 40) * (tick_seconds / self.duration_seconds)
				canvas.create_line(tick_x, bar_y + 6, tick_x, bar_y + 11, fill="#5a7182", width=1)
				canvas.create_text(
					tick_x,
					bar_y + 15,
					text=format_time(self._timeline_seconds(tick_seconds)),
					fill=TEXT_MUTED,
					font=("Segoe UI", 8),
				)

			current_x = 20 + (width - 40) * (self.current_time_seconds / self.duration_seconds)
			canvas.create_line(20, bar_y, current_x, bar_y, fill=ACCENT, width=6)
			canvas.create_oval(current_x - 7, bar_y - 7, current_x + 7, bar_y + 7, fill=ACCENT, outline="")
			for record in self.timeline_records:
				x = 20 + (width - 40) * (record.time_seconds / self.duration_seconds)
				marker_color = "#4da3ff" if record.team == "홈" else "#ff8c69"
				if record.action == "교체":
					canvas.create_line(x, bar_y - 32, x, bar_y - 10, fill=marker_color, width=2)
					canvas.create_text(x, bar_y - 36, text="교체", fill=marker_color, font=("Segoe UI", 9, "bold"), anchor="s")
				else:
					canvas.create_line(x, bar_y - 18, x, bar_y - 2, fill=marker_color, width=2)
					canvas.create_oval(x - 4, bar_y - 26, x + 4, bar_y - 18, fill=marker_color, outline="")
		else:
			canvas.create_text(width / 2, bar_y, text="영상이 없어서 타임라인을 표시할 수 없습니다", fill=TEXT_MUTED)

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

	def _display_frame(self, frame) -> None:
		if Image is None or ImageTk is None:
			raise RuntimeError("Pillow(PIL)가 설치되어 있지 않습니다.")

		canvas_width = max(1, self.video_panel.winfo_width() - 12)
		canvas_height = max(1, self.video_panel.winfo_height() - 12)
		if canvas_width < 50 or canvas_height < 50:
			canvas_width = 960
			canvas_height = 540

		frame_h, frame_w = frame.shape[:2]
		scale = min(canvas_width / frame_w, canvas_height / frame_h)
		target_w = max(1, int(frame_w * scale))
		target_h = max(1, int(frame_h * scale))

		if target_w != frame_w or target_h != frame_h:
			interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
			frame = cv2.resize(frame, (target_w, target_h), interpolation=interpolation)

		frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
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
		if self.video_capture is None or not self.is_playing:
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
		if frames_to_advance > MAX_DECODE_FRAMES_PER_TICK:
			target_index = self.current_frame_index + frames_to_advance - 1
			if self.video_frame_count > 0:
				target_index = min(target_index, self.video_frame_count - 1)
			self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, target_index))
			success, frame = self.video_capture.read()
			if not success:
				self.pause_video()
				self.current_time_seconds = self.duration_seconds
				self._set_seek_value(self.duration_seconds)
				self._update_time_label()
				return
			latest_frame = frame
			self.current_frame_index = target_index + 1
			self.current_time_seconds = self.current_frame_index / self.video_fps if self.video_fps > 0 else self.current_time_seconds
		else:
			for _ in range(frames_to_advance):
				success, frame = self.video_capture.read()
				if not success:
					self.pause_video()
					self.current_time_seconds = self.duration_seconds
					self._set_seek_value(self.duration_seconds)
					self._update_time_label()
					return
				latest_frame = frame
				self.current_frame_index += 1
				self.current_time_seconds = self.current_frame_index / self.video_fps if self.video_fps > 0 else self.current_time_seconds
				if self.video_frame_count > 0 and self.current_frame_index >= self.video_frame_count:
					break

		if latest_frame is not None:
			self._display_frame(latest_frame)
			self._set_seek_value(self.current_time_seconds)
			self._update_time_label()
			self._redraw_timeline()
			if self.video_frame_count > 0 and self.current_frame_index >= self.video_frame_count:
				self.pause_video()

	def _tick(self) -> None:
		if self.is_playing and not self.is_scrubbing:
			self._advance_playback()
		self.after(15, self._tick)

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
		self._release_video()
		self.destroy()


def main() -> None:
	if cv2 is None:
		show_error("영상 재생", "OpenCV(cv2)가 설치되어 있지 않습니다.")
		return
	if Image is None or ImageTk is None:
		show_error("영상 재생", "Pillow(PIL)가 설치되어 있지 않습니다.")
		return

	app = VideoPlayerApp()
	app.mainloop()


if __name__ == "__main__":
	main()
