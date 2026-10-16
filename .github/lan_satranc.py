import json
import socket
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog
import chess

# Windows yerleşik ses kütüphanesi (Harici dosya gerektirmez)
try:
    import winsound

    HAS_SOUND = True
except ImportError:
    HAS_SOUND = False

PIECE_SYMBOLS = {
    "P": "♙",
    "N": "♘",
    "B": "♗",
    "R": "♖",
    "Q": "♕",
    "K": "♔",
    "p": "♟",
    "n": "♞",
    "b": "♝",
    "r": "♜",
    "q": "♛",
    "k": "♚",
}

BROADCAST_PORT = 5556
SQUARE_SIZE = 72
BOARD_SIZE = SQUARE_SIZE * 8


def play_sound(effect_type):
    if not HAS_SOUND:
        return

    def _sound_worker():
        try:
            if effect_type == "move":
                winsound.Beep(600, 65)
            elif effect_type == "capture":
                winsound.Beep(450, 70)
                winsound.Beep(750, 65)
            elif effect_type == "check":
                winsound.Beep(880, 120)
                winsound.Beep(880, 140)
            elif effect_type == "chat":
                winsound.Beep(950, 45)
            elif effect_type == "gameover":
                winsound.Beep(523, 130)
                winsound.Beep(659, 130)
                winsound.Beep(784, 260)
        except Exception:
            pass

    threading.Thread(target=_sound_worker, daemon=True).start()


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


def format_time(seconds):
    seconds = max(0, int(seconds))
    mins, secs = divmod(seconds, 60)
    return f"{mins:02d}:{secs:02d}"


class LANChessApp:

    def __init__(self, root):
        self.root = root
        self.root.title("LAN Satranç - Saatli, Sesli ve Sohbetli")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e272e")

        self.username = ""
        self.opponent_name = "Rakip"
        self.my_color = chess.WHITE
        self.board = chess.Board()
        self.selected_square = None

        self.initial_time = 10 * 60
        self.white_time = self.initial_time
        self.black_time = self.initial_time
        self.clock_job = None
        self.is_game_active = False

        self.server_socket = None
        self.conn_socket = None
        self.is_connected = False
        self.is_hosting = False
        self.stop_broadcast = False

        self.build_lobby_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_lobby_ui(self):
        self.clear_window()
        frame = tk.Frame(self.root, bg="#1e272e", padx=30, pady=22)
        frame.pack()

        tk.Label(
            frame,
            text="♟ LAN SATRANÇ LOBİSİ",
            font=("Segoe UI", 18, "bold"),
            fg="#f5f6fa",
            bg="#1e272e",
        ).pack(pady=(0, 15))

        tk.Label(
            frame,
            text="Kullanıcı Adınız:",
            font=("Segoe UI", 11),
            fg="#dcdde1",
            bg="#1e272e",
        ).pack(anchor="w")
        self.entry_name = tk.Entry(
            frame,
            font=("Segoe UI", 12),
            width=30,
            bg="#2f3640",
            fg="white",
            insertbackground="white",
        )
        self.entry_name.insert(0, "Oyuncu1")
        self.entry_name.pack(pady=(4, 10), ipady=4)

        tk.Label(
            frame,
            text="Oda Portu:",
            font=("Segoe UI", 11),
            fg="#dcdde1",
            bg="#1e272e",
        ).pack(anchor="w")
        self.entry_port = tk.Entry(
            frame,
            font=("Segoe UI", 12),
            width=30,
            bg="#2f3640",
            fg="white",
            insertbackground="white",
        )
        self.entry_port.insert(0, "5555")
        self.entry_port.pack(pady=(4, 15), ipady=4)

        # Oda Kurma Bölümü & Süre Seçimi
        host_frame = tk.LabelFrame(
            frame,
            text=" Yeni Oda Kur (Beyaz) ",
            font=("Segoe UI", 10, "bold"),
            fg="#4cd137",
            bg="#1e272e",
            padx=15,
            pady=10,
        )
        host_frame.pack(fill="x", pady=(0, 15))

        local_ip = get_local_ip()
        tk.Label(
            host_frame,
            text=f"Yerel IP Adresiniz: {local_ip}",
            font=("Segoe UI", 10),
            fg="#00a8ff",
            bg="#1e272e",
        ).pack(pady=(0, 8))

        tk.Label(
            host_frame,
            text="Oyun Süresi Seçimi:",
            font=("Segoe UI", 10),
            fg="#dcdde1",
            bg="#1e272e",
        ).pack(anchor="w")

        time_box = tk.Frame(host_frame, bg="#1e272e")
        time_box.pack(fill="x", pady=(4, 10))

        self.time_var = tk.IntVar(value=10)
        for mins in (3, 5, 10, 15):
            rb = tk.Radiobutton(
                time_box,
                text=f"{mins} Dk",
                variable=self.time_var,
                value=mins,
                font=("Segoe UI", 10, "bold"),
                bg="#1e272e",
                fg="#f5f6fa",
                selectcolor="#2f3640",
                activebackground="#1e272e",
                activeforeground="#4cd137",
                cursor="hand2",
            )
            rb.pack(side="left", expand=True)

        self.btn_host = tk.Button(
            host_frame,
            text="Oda Kur ve Oyuncu Bekle",
            font=("Segoe UI", 11, "bold"),
            bg="#44bd32",
            fg="white",
            activebackground="#4cd137",
            cursor="hand2",
            command=self.start_hosting,
        )
        self.btn_host.pack(fill="x", ipady=4)

        # Odaya Katılma Bölümü
        join_frame = tk.LabelFrame(
            frame,
            text=" Açık Odaya Katıl (Siyah) ",
            font=("Segoe UI", 10, "bold"),
            fg="#00a8ff",
            bg="#1e272e",
            padx=15,
            pady=10,
        )
        join_frame.pack(fill="x")

        tk.Label(
            join_frame,
            text="Oda Sahibinin IP Adresi:",
            font=("Segoe UI", 10),
            fg="#dcdde1",
            bg="#1e272e",
        ).pack(anchor="w")
        self.entry_ip = tk.Entry(
            join_frame,
            font=("Segoe UI", 11),
            bg="#2f3640",
            fg="white",
            insertbackground="white",
        )
        self.entry_ip.insert(0, local_ip)
        self.entry_ip.pack(fill="x", pady=(4, 8), ipady=3)

        btn_scan = tk.Button(
            join_frame,
            text="🔍 Ağdaki Açık Odayı Otomatik Bul",
            font=("Segoe UI", 9),
            bg="#718093",
            fg="white",
            cursor="hand2",
            command=self.scan_lan_rooms,
        )
        btn_scan.pack(fill="x", pady=(0, 8), ipady=2)

        self.btn_join = tk.Button(
            join_frame,
            text="Odaya Katıl (Join)",
            font=("Segoe UI", 11, "bold"),
            bg="#0097e6",
            fg="white",
            activebackground="#00a8ff",
            cursor="hand2",
            command=self.join_room,
        )
        self.btn_join.pack(fill="x", ipady=4)

        self.lbl_status = tk.Label(
            frame,
            text="Hazır.",
            font=("Segoe UI", 10),
            fg="#fbc531",
            bg="#1e272e",
            pady=10,
        )
        self.lbl_status.pack()

    def start_hosting(self):
        self.username = self.entry_name.get().strip() or "Kurucu"
        try:
            port = int(self.entry_port.get().strip())
        except ValueError:
            messagebox.showerror("Hata", "Geçerli bir port numarası girin!")
            return

        selected_mins = self.time_var.get()
        self.initial_time = selected_mins * 60
        self.is_hosting = True
        self.my_color = chess.WHITE
        self.btn_host.config(state="disabled", text="Bekleniyor...")
        self.btn_join.config(state="disabled")
        self.lbl_status.config(
            text=f"Oda kuruldu ({get_local_ip()}:{port} - {selected_mins} Dk). Rakip bekleniyor..."
        )

        threading.Thread(
            target=self._host_thread, args=(port,), daemon=True
        ).start()
        threading.Thread(
            target=self._udp_broadcast_thread,
            args=(port, selected_mins),
            daemon=True,
        ).start()

    def _udp_broadcast_thread(self, game_port, mins):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps({
            "host": self.username,
            "ip": get_local_ip(),
            "port": game_port,
            "mins": mins,
        }).encode("utf-8")

        while not self.stop_broadcast and not self.is_connected:
            try:
                udp_sock.sendto(payload, ("<broadcast>", BROADCAST_PORT))
            except Exception:
                pass
            threading.Event().wait(1.5)
        udp_sock.close()

    def scan_lan_rooms(self):
        self.lbl_status.config(text="Yerel ağdaki açık odalar taranıyor...")
        threading.Thread(target=self._scan_thread, daemon=True).start()

    def _scan_thread(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.settimeout(3.0)
        try:
            udp_sock.bind(("", BROADCAST_PORT))
            data, _ = udp_sock.recvfrom(1024)
            info = json.loads(data.decode("utf-8"))
            self.root.after(0, lambda: self._fill_room_info(info))
        except socket.timeout:
            self.root.after(
                0,
                lambda: self.lbl_status.config(
                    text="Açık oda bulunamadı. IP adresini elle girebilirsiniz."
                ),
            )
        except Exception as e:
            self.root.after(
                0, lambda: self.lbl_status.config(text=f"Tarama hatası: {e}")
            )
        finally:
            udp_sock.close()

    def _fill_room_info(self, info):
        self.entry_ip.delete(0, tk.END)
        self.entry_ip.insert(0, info["ip"])
        self.entry_port.delete(0, tk.END)
        self.entry_port.insert(0, str(info["port"]))
        mins = info.get("mins", 10)
        self.lbl_status.config(
            text=f"Bulundu: '{info['host']}' odası ({mins} Dk - {info['ip']}:{info['port']})"
        )

    def _host_thread(self, port):
        try:
            self.server_socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM
            )
            self.server_socket.setsockopt(
                socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
            )
            self.server_socket.bind(("0.0.0.0", port))
            self.server_socket.listen(1)

            conn, _ = self.server_socket.accept()
            self.conn_socket = conn
            self.is_connected = True
            self.stop_broadcast = True

            self.send_json({
                "type": "hello",
                "name": self.username,
                "initial_time": self.initial_time,
            })
            threading.Thread(target=self.receive_loop, daemon=True).start()
            self.root.after(0, self.build_game_ui)
        except Exception as e:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Sunucu Hatası", f"Oda başlatılamadı:\n{e}"
                ),
            )

    def join_room(self):
        self.username = self.entry_name.get().strip() or "Misafir"
        target_ip = self.entry_ip.get().strip()
        try:
            port = int(self.entry_port.get().strip())
        except ValueError:
            messagebox.showerror("Hata", "Geçerli bir port numarası girin!")
            return

        self.my_color = chess.BLACK
        self.lbl_status.config(text=f"{target_ip}:{port} adresine bağlanılıyor...")
        threading.Thread(
            target=self._join_thread, args=(target_ip, port), daemon=True
        ).start()

    def _join_thread(self, ip, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ip, port))
            sock.settimeout(None)

            self.conn_socket = sock
            self.is_connected = True

            self.send_json({"type": "hello", "name": self.username})
            threading.Thread(target=self.receive_loop, daemon=True).start()
            self.root.after(0, self.build_game_ui)
        except Exception as e:
            self.root.after(
                0,
                lambda: messagebox.showerror(
                    "Bağlantı Hatası", f"Odaya bağlanılamadı:\n{e}"
                ),
            )
            self.root.after(
                0,
                lambda: self.lbl_status.config(text="Bağlantı başarısız oldu."),
            )

    def send_json(self, data):
        if self.conn_socket and self.is_connected:
            try:
                msg = (json.dumps(data) + "\n").encode("utf-8")
                self.conn_socket.sendall(msg)
            except Exception:
                pass

    def receive_loop(self):
        buffer = ""
        while self.is_connected:
            try:
                chunk = self.conn_socket.recv(1024).decode("utf-8")
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        self.root.after(
                            0, lambda m=msg: self.handle_network_message(m)
                        )
            except Exception:
                break
        self.is_connected = False
        self.root.after(0, self.on_disconnect)

    def handle_network_message(self, msg):
        msg_type = msg.get("type")
        if msg_type == "hello":
            self.opponent_name = msg.get("name", "Rakip")
            if "initial_time" in msg:
                self.initial_time = int(msg["initial_time"])
                self.white_time = self.initial_time
                self.black_time = self.initial_time
                if hasattr(self, "clock_frame"):
                    self.clock_frame.config(
                        text=f" ⏱ Satranç Saati ({self.initial_time // 60} Dk) "
                    )
                self.update_clock_labels()
            self.update_info_bar()
            self.append_chat(
                "Sistem",
                f"{self.opponent_name} odaya katıldı ({self.initial_time // 60} dk). Oyun başladı!",
                "sys",
            )
            play_sound("move")

        elif msg_type == "move":
            uci = msg.get("uci")
            move = chess.Move.from_uci(uci)
            if move in self.board.legal_moves:
                is_capture = self.board.is_capture(move)
                san_move = self.board.san(move)
                self.board.push(move)

                self.white_time = msg.get("w_time", self.white_time)
                self.black_time = msg.get("b_time", self.black_time)
                self.selected_square = None
                self.draw_board()
                self.update_info_bar()
                self.update_clock_labels()
                self.append_chat(
                    "Sistem", f"{self.opponent_name} hamlesi: {san_move}", "sys"
                )
                self.trigger_move_sound_and_check(is_capture)

        elif msg_type == "chat":
            sender = msg.get("sender", self.opponent_name)
            text = msg.get("text", "")
            self.append_chat(sender, text, "opp")
            play_sound("chat")

        elif msg_type == "timeout":
            loser_color = msg.get("loser")
            self.handle_timeout_end(loser_color)

        elif msg_type == "reset":
            if "initial_time" in msg:
                self.initial_time = int(msg["initial_time"])
            self.reset_local_state()
            self.append_chat(
                "Sistem",
                f"{self.opponent_name} yeni bir oyun başlattı.",
                "sys",
            )
            play_sound("move")

    def on_disconnect(self):
        self.stop_clock()
        messagebox.showwarning("Bağlantı Kesildi", "Rakip oyundan ayrıldı.")
        self.root.destroy()

    def build_game_ui(self):
        self.clear_window()

        main_container = tk.Frame(self.root, bg="#1e272e", padx=12, pady=12)
        main_container.pack(fill="both", expand=True)

        left_panel = tk.Frame(main_container, bg="#1e272e")
        left_panel.pack(side="left", padx=(0, 12))

        top_bar = tk.Frame(left_panel, bg="#2f3640", padx=12, pady=8)
        top_bar.pack(fill="x")

        self.lbl_players = tk.Label(
            top_bar,
            text="",
            font=("Segoe UI", 11, "bold"),
            fg="#f5f6fa",
            bg="#2f3640",
        )
        self.lbl_players.pack(side="left")

        btn_reset = tk.Button(
            top_bar,
            text="Yeni Oyun",
            font=("Segoe UI", 9, "bold"),
            bg="#e1b12c",
            fg="#1e272e",
            cursor="hand2",
            command=self.reset_game,
        )
        btn_reset.pack(side="right")

        self.lbl_turn = tk.Label(
            left_panel,
            text="",
            font=("Segoe UI", 11, "bold"),
            fg="#4cd137",
            bg="#1e272e",
            pady=6,
        )
        self.lbl_turn.pack(fill="x")

        self.canvas = tk.Canvas(
            left_panel,
            width=BOARD_SIZE,
            height=BOARD_SIZE,
            highlightthickness=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_square_click)

        right_panel = tk.Frame(main_container, bg="#1e272e", width=290)
        right_panel.pack(side="right", fill="y")
        right_panel.pack_propagate(False)

        self.clock_frame = tk.LabelFrame(
            right_panel,
            text=f" ⏱ Satranç Saati ({self.initial_time // 60} Dk) ",
            font=("Segoe UI", 10, "bold"),
            fg="#fbc531",
            bg="#1e272e",
            padx=10,
            pady=8,
        )
        self.clock_frame.pack(fill="x", pady=(0, 10))

        w_row = tk.Frame(self.clock_frame, bg="#2f3640", padx=10, pady=6)
        w_row.pack(fill="x", pady=(0, 6))
        self.lbl_white_title = tk.Label(
            w_row,
            text="♔ Beyaz:",
            font=("Segoe UI", 10, "bold"),
            fg="#f5f6fa",
            bg="#2f3640",
        )
        self.lbl_white_title.pack(side="left")
        self.lbl_white_clock = tk.Label(
            w_row,
            text=format_time(self.initial_time),
            font=("Consolas", 16, "bold"),
            fg="#4cd137",
            bg="#2f3640",
        )
        self.lbl_white_clock.pack(side="right")

        b_row = tk.Frame(self.clock_frame, bg="#2f3640", padx=10, pady=6)
        b_row.pack(fill="x")
        self.lbl_black_title = tk.Label(
            b_row,
            text="♚ Siyah:",
            font=("Segoe UI", 10, "bold"),
            fg="#dcdde1",
            bg="#2f3640",
        )
        self.lbl_black_title.pack(side="left")
        self.lbl_black_clock = tk.Label(
            b_row,
            text=format_time(self.initial_time),
            font=("Consolas", 16, "bold"),
            fg="#dcdde1",
            bg="#2f3640",
        )
        self.lbl_black_clock.pack(side="right")

        chat_frame = tk.LabelFrame(
            right_panel,
            text=" 💬 Oyun İçi Sohbet ",
            font=("Segoe UI", 10, "bold"),
            fg="#00a8ff",
            bg="#1e272e",
            padx=8,
            pady=8,
        )
        chat_frame.pack(fill="both", expand=True)

        self.chat_area = scrolledtext.ScrolledText(
            chat_frame,
            wrap=tk.WORD,
            state="disabled",
            bg="#2f3640",
            fg="#f5f6fa",
            font=("Segoe UI", 9),
            bd=0,
            padx=6,
            pady=6,
        )
        self.chat_area.pack(fill="both", expand=True, pady=(0, 8))

        self.chat_area.tag_config(
            "me", foreground="#00a8ff", font=("Segoe UI", 9, "bold")
        )
        self.chat_area.tag_config(
            "opp", foreground="#4cd137", font=("Segoe UI", 9, "bold")
        )
        self.chat_area.tag_config(
            "sys", foreground="#fbc531", font=("Segoe UI", 9, "italic")
        )

        input_frame = tk.Frame(chat_frame, bg="#1e272e")
        input_frame.pack(fill="x")

        self.entry_chat = tk.Entry(
            input_frame,
            font=("Segoe UI", 10),
            bg="#2f3640",
            fg="white",
            insertbackground="white",
        )
        self.entry_chat.pack(
            side="left", fill="x", expand=True, ipady=4, padx=(0, 6)
        )
        self.entry_chat.bind("<Return>", self.send_chat_message)

        btn_send = tk.Button(
            input_frame,
            text="Gönder",
            font=("Segoe UI", 9, "bold"),
            bg="#0097e6",
            fg="white",
            activebackground="#00a8ff",
            cursor="hand2",
            command=self.send_chat_message,
        )
        btn_send.pack(side="right", ipady=2, ipadx=6)

        self.reset_local_state()

    def start_clock(self):
        self.stop_clock()
        self.is_game_active = True
        self.tick_clock()

    def stop_clock(self):
        self.is_game_active = False
        if self.clock_job is not None:
            self.root.after_cancel(self.clock_job)
            self.clock_job = None

    def tick_clock(self):
        if not self.is_game_active or self.board.is_game_over():
            return

        if self.board.turn == chess.WHITE:
            self.white_time -= 1
            if self.white_time <= 0:
                self.white_time = 0
                self.update_clock_labels()
                self.send_json({"type": "timeout", "loser": "white"})
                self.handle_timeout_end("white")
                return
        else:
            self.black_time -= 1
            if self.black_time <= 0:
                self.black_time = 0
                self.update_clock_labels()
                self.send_json({"type": "timeout", "loser": "black"})
                self.handle_timeout_end("black")
                return

        self.update_clock_labels()
        self.clock_job = self.root.after(1000, self.tick_clock)

    def update_clock_labels(self):
        if not hasattr(self, "lbl_white_clock"):
            return

        self.lbl_white_clock.config(text=format_time(self.white_time))
        self.lbl_black_clock.config(text=format_time(self.black_time))

        if self.board.turn == chess.WHITE:
            w_color = "#e84118" if self.white_time < 60 else "#4cd137"
            self.lbl_white_clock.config(fg=w_color)
            self.lbl_black_clock.config(fg="#7f8fa6")
        else:
            b_color = "#e84118" if self.black_time < 60 else "#4cd137"
            self.lbl_black_clock.config(fg=b_color)
            self.lbl_white_clock.config(fg="#7f8fa6")

    def handle_timeout_end(self, loser_color):
        self.stop_clock()
        self.update_clock_labels()
        play_sound("gameover")
        if loser_color == "white":
            msg = "Beyazın süresi bitti! Siyah kazandı."
        else:
            msg = "Siyahın süresi bitti! Beyaz kazandı."
        self.lbl_turn.config(text=f"⌛ {msg}", fg="#e84118")
        self.append_chat("Sistem", msg, "sys")
        messagebox.showinfo("Süre Bitti", msg)

    def send_chat_message(self, event=None):
        text = self.entry_chat.get().strip()
        if not text:
            return
        self.entry_chat.delete(0, tk.END)
        self.append_chat(self.username, text, "me")
        self.send_json({"type": "chat", "sender": self.username, "text": text})

    def append_chat(self, sender, text, tag):
        if not hasattr(self, "chat_area"):
            return
        self.chat_area.config(state="normal")
        if tag == "sys":
            self.chat_area.insert(tk.END, f"• {text}\n", "sys")
        else:
            self.chat_area.insert(tk.END, f"{sender}: ", tag)
            self.chat_area.insert(tk.END, f"{text}\n")
        self.chat_area.see(tk.END)
        self.chat_area.config(state="disabled")

    def update_info_bar(self):
        if not hasattr(self, "lbl_players"):
            return
        white_name = (
            self.username
            if self.my_color == chess.WHITE
            else self.opponent_name
        )
        black_name = (
            self.opponent_name
            if self.my_color == chess.WHITE
            else self.username
        )
        self.lbl_players.config(
            text=f"♔ {white_name} (Beyaz)   vs   ♚ {black_name} (Siyah)"
        )

        if hasattr(self, "lbl_white_title"):
            self.lbl_white_title.config(text=f"♔ {white_name}:")
            self.lbl_black_title.config(text=f"♚ {black_name}:")

        if self.board.turn == self.my_color:
            self.lbl_turn.config(
                text="▶ SIRA SENDE (Hamle yapın)", fg="#4cd137"
            )
        else:
            self.lbl_turn.config(
                text=f"⏳ {self.opponent_name} düşünülüyor...", fg="#fbc531"
            )

    def draw_board(self):
        self.canvas.delete("all")
        legal_targets = []
        if self.selected_square is not None:
            legal_targets = [
                m.to_square
                for m in self.board.legal_moves
                if m.from_square == self.selected_square
            ]

        for row in range(8):
            for col in range(8):
                rank = 7 - row if self.my_color == chess.WHITE else row
                file = col if self.my_color == chess.WHITE else 7 - col
                sq = chess.square(file, rank)

                x1, y1 = col * SQUARE_SIZE, row * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE

                is_light = (rank + file) % 2 == 1
                bg_color = "#f0d9b5" if is_light else "#b58863"

                if sq == self.selected_square:
                    bg_color = "#f7f769"
                elif self.board.move_stack:
                    last_move = self.board.peek()
                    if sq in (last_move.from_square, last_move.to_square):
                        bg_color = "#cdd26a"

                self.canvas.create_rectangle(
                    x1, y1, x2, y2, fill=bg_color, outline=""
                )

                if sq in legal_targets:
                    cx, cy = x1 + SQUARE_SIZE // 2, y1 + SQUARE_SIZE // 2
                    self.canvas.create_oval(
                        cx - 9,
                        cx - 9,
                        cx + 9,
                        cx + 9,
                        fill="#2ecc71",
                        outline="",
                    )

                piece = self.board.piece_at(sq)
                if piece:
                    symbol = PIECE_SYMBOLS[piece.symbol()]
                    p_color = (
                        "#ffffff" if piece.color == chess.WHITE else "#111111"
                    )
                    self.canvas.create_text(
                        x1 + SQUARE_SIZE // 2 + 1,
                        y1 + SQUARE_SIZE // 2 + 1,
                        text=symbol,
                        font=("Segoe UI Symbol", 38),
                        fill="#555555",
                    )
                    self.canvas.create_text(
                        x1 + SQUARE_SIZE // 2,
                        y1 + SQUARE_SIZE // 2,
                        text=symbol,
                        font=("Segoe UI Symbol", 38),
                        fill=p_color,
                    )

    def on_square_click(self, event):
        if (
            not self.is_game_active
            or self.board.turn != self.my_color
            or self.board.is_game_over()
        ):
            return

        col = event.x // SQUARE_SIZE
        row = event.y // SQUARE_SIZE
        rank = 7 - row if self.my_color == chess.WHITE else row
        file = col if self.my_color == chess.WHITE else 7 - col
        clicked_sq = chess.square(file, rank)

        if self.selected_square is None:
            piece = self.board.piece_at(clicked_sq)
            if piece and piece.color == self.my_color:
                self.selected_square = clicked_sq
                self.draw_board()
        else:
            move = self.find_move(self.selected_square, clicked_sq)
            if move:
                is_capture = self.board.is_capture(move)
                san_move = self.board.san(move)
                self.board.push(move)
                self.selected_square = None
                self.draw_board()
                self.update_info_bar()
                self.update_clock_labels()
                self.append_chat(
                    "Sistem", f"Senin hamlen: {san_move}", "sys"
                )
                self.send_json({
                    "type": "move",
                    "uci": move.uci(),
                    "w_time": self.white_time,
                    "b_time": self.black_time,
                })
                self.trigger_move_sound_and_check(is_capture)
            else:
                piece = self.board.piece_at(clicked_sq)
                if piece and piece.color == self.my_color:
                    self.selected_square = clicked_sq
                else:
                    self.selected_square = None
                self.draw_board()

    def find_move(self, from_sq, to_sq):
        promo_move = chess.Move(from_sq, to_sq, promotion=chess.QUEEN)
        if promo_move in self.board.legal_moves:
            choice = simpledialog.askstring(
                "Piyon Terfisi",
                "Terfi edilecek taşı seçin (V: Vezir, K: Kale, F: Fil, A: At):",
                initialvalue="V",
            )
            mapping = {
                "K": chess.ROOK,
                "F": chess.BISHOP,
                "A": chess.KNIGHT,
                "V": chess.QUEEN,
            }
            promo_piece = mapping.get((choice or "V").upper(), chess.QUEEN)
            return chess.Move(from_sq, to_sq, promotion=promo_piece)

        normal_move = chess.Move(from_sq, to_sq)
        if normal_move in self.board.legal_moves:
            return normal_move
        return None

    def trigger_move_sound_and_check(self, is_capture):
        if self.board.is_checkmate():
            self.stop_clock()
            play_sound("gameover")
            winner = "Beyaz" if self.board.turn == chess.BLACK else "Siyah"
            msg = f"Şah Mat! {winner} kazandı."
            self.lbl_turn.config(text=f"🏆 {msg}", fg="#4cd137")
            self.append_chat("Sistem", msg, "sys")
            messagebox.showinfo("Oyun Bitti", msg)
        elif self.board.is_stalemate() or self.board.is_insufficient_material():
            self.stop_clock()
            play_sound("gameover")
            msg = "Oyun Berabere (Pat) bitti!"
            self.lbl_turn.config(text=f"🤝 {msg}", fg="#fbc531")
            self.append_chat("Sistem", msg, "sys")
            messagebox.showinfo("Oyun Bitti", msg)
        elif self.board.is_check():
            play_sound("check")
            self.lbl_turn.config(text="⚠️ ŞAH ÇEKİLDİ!", fg="#e84118")
        elif is_capture:
            play_sound("capture")
        else:
            play_sound("move")

    def reset_local_state(self):
        self.board.reset()
        self.selected_square = None
        self.white_time = self.initial_time
        self.black_time = self.initial_time
        self.draw_board()
        self.update_info_bar()
        self.update_clock_labels()
        self.start_clock()

    def reset_game(self):
        self.reset_local_state()
        self.append_chat("Sistem", "Yeni bir oyun başlattınız.", "sys")
        self.send_json({"type": "reset", "initial_time": self.initial_time})
        play_sound("move")

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    def on_close(self):
        self.stop_clock()
        self.stop_broadcast = True
        self.is_connected = False
        try:
            if self.conn_socket:
                self.conn_socket.close()
            if self.server_socket:
                self.server_socket.close()
        except Exception:
            pass
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = LANChessApp(root)
    root.mainloop()