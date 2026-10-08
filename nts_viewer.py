import ctypes
import json
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path

from nts_scrape import GROUPS, TABS, fetch_all

# exe로 실행 시: 아이콘은 exe 내부 임시폴더, 읽은 기록은 exe 옆에 저장
if getattr(sys, "frozen", False):
    RES_DIR = Path(sys._MEIPASS)
    DATA_DIR = Path(sys.executable).parent
else:
    RES_DIR = DATA_DIR = Path(__file__).parent
READ_FILE = DATA_DIR / "nts_read.json"
ICON_FILE = RES_DIR / "radar.ico"
LOGO_FILE = RES_DIR / "radar_small.png"

# 작업표시줄에서 python 아이콘 대신 앱 아이콘이 보이도록 별도 앱으로 등록
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Beodeul.NtsRadar")

# 색상 (아이콘의 남색 + 레이더 초록)
NAVY = "#0a1e37"
NAVY_LIGHT = "#16325a"
GREEN = "#3ccf8e"
BG = "#f3f5f9"
CARD = "#ffffff"
HOVER = "#eefaf4"
LINE = "#e6e9ef"
TEXT = "#1f2937"
TEXT_READ = "#8a93a3"
SUB = "#9aa4b5"
BADGE = {"보도": "#2563eb", "설명": "#0891b2", "공지": "#7c3aed", "고시": "#ea580c", "공고": "#059669", "세제": "#b45309", "해석": "#0d9488", "심판": "#be185d", "판례": "#4f46e5", "법령": "#475569"}

FONT = "맑은 고딕"


def load_read():
    try:
        return set(json.loads(READ_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError):
        return set()


class RadarApp:
    def __init__(self, root):
        self.root = root
        self.read_ids = load_read()
        self.data = {tab: [] for tab in TABS}
        self.group = next(iter(GROUPS))
        self.last_tab = {g: tabs[0] for g, tabs in GROUPS.items()}  # 묶음별 마지막으로 본 탭
        self.current = self.last_tab[self.group]
        self.loading = False
        self.failed = []

        root.title("국세레이더 - 국세청 새 소식")
        root.geometry("960x620")
        root.minsize(640, 420)
        root.configure(bg=BG)
        root.iconbitmap(default=str(ICON_FILE))

        self._build_header()
        self._build_tabs()
        self._build_list()
        self._build_footer()
        self.refresh()

    # ---------- 화면 구성 ----------
    def _build_header(self):
        header = tk.Frame(self.root, bg=NAVY, padx=22, pady=16)
        header.pack(fill="x")

        self.logo = tk.PhotoImage(file=str(LOGO_FILE))
        tk.Label(header, image=self.logo, bg=NAVY).pack(side="left")

        titles = tk.Frame(header, bg=NAVY, padx=12)
        titles.pack(side="left")
        tk.Label(titles, text="국세레이더", font=(FONT, 16, "bold"), fg="white", bg=NAVY).pack(anchor="w")
        self.status = tk.Label(titles, text="국세청 새 소식을 확인하는 중…", font=(FONT, 9), fg=SUB, bg=NAVY)
        self.status.pack(anchor="w")

        self.refresh_btn = self._button(header, "⟳  새로고침", self.refresh, NAVY_LIGHT, GREEN, "white", NAVY)
        self.refresh_btn.pack(side="right")
        self.read_all_btn = self._button(header, "✓  모두 읽음", self.mark_all_read, NAVY, NAVY_LIGHT, SUB, "white")
        self.read_all_btn.pack(side="right", padx=(0, 8))

    def _build_tabs(self):
        bar = tk.Frame(self.root, bg=NAVY, padx=18)
        bar.pack(fill="x")

        # 묶음 전환 버튼 (소식 / 법령정보)
        seg = tk.Frame(bar, bg=NAVY_LIGHT, padx=3, pady=3)
        seg.pack(side="left", pady=(4, 7))
        self.group_widgets = {}
        for g in GROUPS:
            pill = tk.Frame(seg, bg=NAVY_LIGHT, cursor="hand2")
            pill.pack(side="left")
            name = tk.Label(pill, text=g, font=(FONT, 9, "bold"), padx=12, pady=3, bg=NAVY_LIGHT, fg=SUB)
            name.pack(side="left")
            dot = tk.Label(pill, text="●", font=(FONT, 7), bg=NAVY_LIGHT, fg=GREEN)
            for w in (pill, name, dot):
                w.bind("<Button-1>", lambda e, g=g: self.select_group(g))
            self.group_widgets[g] = (pill, name, dot)
        tk.Frame(bar, bg=NAVY_LIGHT, width=1, height=22).pack(side="left", padx=(14, 4), pady=(0, 3))

        self.tabs_frame = tk.Frame(bar, bg=NAVY)
        self.tabs_frame.pack(side="left")
        self.tab_widgets = {}
        for tab in TABS:
            box = tk.Frame(self.tabs_frame, bg=NAVY, cursor="hand2")
            inner = tk.Frame(box, bg=NAVY, padx=10, pady=8)
            inner.pack()
            label = tk.Label(inner, text=tab, font=(FONT, 10), fg=SUB, bg=NAVY)
            label.pack(side="left")
            count = tk.Label(inner, text="", font=(FONT, 8, "bold"), fg=NAVY, bg=GREEN, padx=5)
            underline = tk.Frame(box, height=3, bg=NAVY)
            underline.pack(fill="x")
            for w in (box, inner, label, count):
                w.bind("<Button-1>", lambda e, t=tab: self.select_tab(t))
            self.tab_widgets[tab] = (box, label, count, underline)

    def _build_list(self):
        wrap = tk.Frame(self.root, bg=BG, padx=20, pady=16)
        wrap.pack(fill="both", expand=True)
        card = tk.Frame(wrap, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        card.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(card, bg=CARD, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.list_frame = tk.Frame(self.canvas, bg=CARD)
        win = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.list_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.root.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(-e.delta // 120, "units"))

    def _build_footer(self):
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=22, pady=(0, 12))
        tk.Label(footer, text="●", font=(FONT, 9), fg=GREEN, bg=BG).pack(side="left")
        tk.Label(footer, text=" 아직 안 읽은 글   ·   클릭하면 브라우저로 열립니다",
                 font=(FONT, 9), fg=SUB, bg=BG).pack(side="left")

    def _button(self, parent, text, command, bg, hover_bg, fg, hover_fg):
        btn = tk.Label(parent, text=text, font=(FONT, 10, "bold"), bg=bg, fg=fg, padx=14, pady=6, cursor="hand2")
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover_bg, fg=hover_fg))
        btn.bind("<Leave>", lambda e: btn.configure(bg=bg, fg=fg))
        return btn

    # ---------- 데이터 ----------
    def refresh(self):
        if self.loading:
            return
        self.loading = True
        self.refresh_btn.configure(text="⟳  불러오는 중…")
        threading.Thread(target=self._fetch_all, daemon=True).start()

    def _fetch_all(self):
        try:
            # 일부 사이트가 안 열리면 그 탭은 직전 목록을 유지
            data, errors = fetch_all(fallback=self.data)
            if len(errors) == len(data) - 1:  # '전체'를 뺀 모든 탭 실패
                raise next(iter(errors.values()))
            self.failed = list(errors)
            self.root.after(0, self._on_loaded, data, None)
        except Exception as e:
            self.root.after(0, self._on_loaded, None, e)

    def _on_loaded(self, data, error):
        self.loading = False
        self.refresh_btn.configure(text="⟳  새로고침")
        if error:
            self.status.configure(text=f"불러오기 실패 · 인터넷 연결을 확인해 주세요 ({type(error).__name__})", fg="#f87171")
            return
        self.data = data
        self.updated = datetime.now().strftime("%H:%M")
        self.render()

    def is_unread(self, item):
        return item["id"] not in self.read_ids

    def save_read(self):
        READ_FILE.write_text(json.dumps(sorted(self.read_ids)), encoding="utf-8")

    def open_item(self, item):
        webbrowser.open(item["링크"])
        self.read_ids.add(item["id"])
        self.save_read()
        self.render()

    def mark_all_read(self):
        for items in self.data.values():
            self.read_ids.update(it["id"] for it in items)
        self.save_read()
        self.render()

    def select_tab(self, tab):
        self.current = self.last_tab[self.group] = tab
        self.render()

    def select_group(self, group):
        self.group = group
        self.current = self.last_tab[group]
        self.render()

    # ---------- 그리기 ----------
    def render(self):
        unread_all = {it["id"] for items in self.data.values() for it in items if self.is_unread(it)}
        if hasattr(self, "updated"):
            msg = f"새 글 {len(unread_all)}개" if unread_all else "새 글 없음"
            text = f"{msg}  ·  {self.updated} 업데이트"
            if self.failed:
                text += f"  ·  {', '.join(self.failed)} 연결 실패"
            self.status.configure(text=text, fg=GREEN if unread_all else SUB)

        for g, (pill, name, dot) in self.group_widgets.items():
            active = g == self.group
            bg = GREEN if active else NAVY_LIGHT
            pill.configure(bg=bg)
            name.configure(bg=bg, fg=NAVY if active else SUB)
            # 보고 있지 않은 묶음에 안 읽은 글이 있으면 초록 점
            if not active and any(self.is_unread(it) for tab in GROUPS[g] for it in self.data[tab]):
                dot.pack(side="left", padx=(0, 8))
            else:
                dot.pack_forget()

        for box, *_ in self.tab_widgets.values():
            box.pack_forget()
        for tab in GROUPS[self.group]:
            self.tab_widgets[tab][0].pack(side="left")

        for tab, (box, label, count, underline) in self.tab_widgets.items():
            active = tab == self.current
            label.configure(fg="white" if active else SUB, font=(FONT, 10, "bold" if active else "normal"))
            underline.configure(bg=GREEN if active else NAVY)
            n = sum(self.is_unread(it) for it in self.data[tab])
            if n:
                count.configure(text=str(n))
                count.pack(side="left", padx=(6, 0))
            else:
                count.pack_forget()

        for w in self.list_frame.winfo_children():
            w.destroy()
        items = self.data[self.current]
        if not items:
            tk.Label(self.list_frame, text="표시할 글이 없습니다", font=(FONT, 10), fg=SUB, bg=CARD, pady=40).pack()
        for i, item in enumerate(items):
            self._row(item, last=i == len(items) - 1)
        self.canvas.yview_moveto(0)

    def _row(self, item, last):
        unread = self.is_unread(item)
        row = tk.Frame(self.list_frame, bg=CARD, cursor="hand2")
        row.pack(fill="x")
        body = tk.Frame(row, bg=CARD, padx=18, pady=12)
        body.pack(fill="x")

        dot = tk.Canvas(body, width=10, height=10, bg=CARD, highlightthickness=0)
        if unread:
            dot.create_oval(1, 1, 9, 9, fill=GREEN, outline="")
        dot.pack(side="left", padx=(0, 12))

        badge = tk.Label(body, text=item["구분"], font=(FONT, 8, "bold"), fg="white",
                         bg=BADGE.get(item["구분"], SUB), padx=7, pady=1)
        badge.pack(side="left", padx=(0, 12))

        date = tk.Label(body, text=item["날짜"].rstrip("."), font=(FONT, 9), fg=SUB, bg=CARD)
        date.pack(side="right", padx=(16, 0))

        title = tk.Label(body, text=item["제목"], anchor="w", bg=CARD,
                         font=(FONT, 10, "bold" if unread else "normal"), fg=TEXT if unread else TEXT_READ)
        title.pack(side="left", fill="x", expand=True)

        if not last:
            tk.Frame(row, height=1, bg=LINE).pack(fill="x", padx=18)

        hover_parts = (row, body, dot, date, title)

        def set_bg(color):
            for w in hover_parts:
                w.configure(bg=color)

        for w in hover_parts + (badge,):
            w.bind("<Enter>", lambda e: set_bg(HOVER))
            w.bind("<Leave>", lambda e: set_bg(CARD))
            w.bind("<Button-1>", lambda e: self.open_item(item))


if __name__ == "__main__":
    root = tk.Tk()
    RadarApp(root)
    root.mainloop()
