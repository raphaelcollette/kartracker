import os
import time
import threading
import keyboard
import mss
import mss.tools
import psycopg2
import easyocr
import discord
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import tkinter as tk
from tkinter import messagebox

# Config
SCREENSHOT_DIR = "screenshots"
# add bot info here

# OCR and Database Logic
PLAYERS = ['Starz', 'ray', 'RAPH', 'bran', 'djtrader', 'BAKABAKABAKABAKABAKA',
           'henry', 'Umbrella', 'jem', 'vortex', 'nut', 'bunixmi']

mario_kart_8_deluxe_chars = [
    "Mario", "Luigi", "Peach", "Daisy", "Rosalina", "Tanooki Mario", "Cat Peach",
    "Yoshi", "Toad", "Koopa Troopa", "Shy Guy", "Lakitu", "Toadette", "King Boo",
    "Baby Mario", "Baby Luigi", "Baby Peach", "Baby Daisy", "Baby Rosalina",
    "Metal Mario", "Pink Gold Peach", "Wario", "Waluigi", "Donkey Kong",
    "Bowser", "Dry Bones", "Bowser Jr.", "Dry Bowser",
    "Lemmy", "Larry", "Wendy", "Ludwig",
    "Iggy", "Roy", "Morton",
    "Inkling Girl", "Inkling Boy", "Link", "Villager",
    "Isabelle", "Birdo", "Petey Piranha", "Wiggler", "Kamek",
    "Diddy Kong", "Funky Kong", "Pauline", "Peachette", "Cat Peach", "Lemmy"
]
reader = easyocr.Reader(['en'])

def get_ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def get_results(screenshot):
    parsed_results = []
    raw = reader.readtext(screenshot, detail=0)
    first_match_found = False
    for idx, name in enumerate(raw):
        if name in PLAYERS or name in mario_kart_8_deluxe_chars:
            prev = raw[idx - 1]

            if not first_match_found:
                if prev in ['7', 'I', 'l', '|', 'CONGRATULATIONSI'] or 'CON' in prev:  # OCR mistakes for '1'
                    prev_num = '1'
                elif prev == 'A':
                    prev_num = '4'
                else:
                    prev_num = prev
                first_match_found = True
            else:
                if prev == 'A':
                    prev_num = '4'
                else:
                    prev_num = prev

            try:
                placement = int(prev_num)
                parsed_results.append([placement, name])
            except (ValueError, TypeError):
                print(f"Warning: Could not parse rank for {name} (got: {prev_num})")
                parsed_results.append(['error', name])

    return parsed_results

async def send_leaderboard(channel):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    leaderboard_data = []
    for name in PLAYERS:
        cur.execute('''
            SELECT COUNT(*), AVG(placement), MAX(elo)
            FROM RaceResults
            JOIN Players ON RaceResults.player_id = Players.id
            WHERE Players.mii_name = %s
        ''', (name,))
        result = cur.fetchone()
        if result and result[0] > 0:
            total, avg, elo = result
            leaderboard_data.append((name, total, avg, elo))

    conn.close()

    leaderboard_data.sort(key=lambda x: x[3], reverse=True)

    header = f"{'Name':<20} {'Races':<6} {'Avg':<6} {'Elo':<5}"
    lines = [
        "```markdown",
        header,
        "-" * len(header)
    ]
    for name, total, avg, elo in leaderboard_data:
        lines.append(f"{name:<20} {total:<6} {avg:<6.2f} {elo:<5}")
    lines.append("```")

    await channel.send("\n".join(lines))

async def send_history(channel, mii_name):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute('''
        SELECT placement, timestamp
        FROM RaceResults
        JOIN Players ON RaceResults.player_id = Players.id
        WHERE Players.mii_name = %s
        ORDER BY timestamp DESC
        LIMIT 20
    ''', (mii_name,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await channel.send(f"No race history found for **{mii_name}**.")
        return

    lines = [
        f"```markdown",
        f"Recent Races for {mii_name}",
        f"{'Place':<6} {'Date':<19}",
        "-" * 26
    ]

    for place, ts in rows:
        ts_str = ts.strftime("%Y-%m-%d %H:%M")
        lines.append(f"{place:<6} {ts_str}")

    lines.append("```")
    await channel.send("\n".join(lines))

# GUI review
def review_results_gui(results):
    updated_results = []

    def on_confirm():
        try:
            updated_results.clear()
            for idx in range(len(entry_fields)):
                place = int(entry_fields[idx][0].get())
                name = entry_fields[idx][1].get().strip()
                if name:
                    updated_results.append((place, name))
            window.destroy()
        except ValueError:
            messagebox.showerror("Error", "Placements must be valid numbers.")

    def on_cancel():
        updated_results.clear()
        window.destroy()

    window = tk.Tk()
    window.title("Review OCR Results")
    window.geometry("300x400")
    window.resizable(False, False)

    frame = tk.Frame(window)
    frame.pack(pady=10)

    tk.Label(frame, text="Placement", font=('Arial', 10, 'bold')).grid(row=0, column=0)
    tk.Label(frame, text="Player", font=('Arial', 10, 'bold')).grid(row=0, column=1)

    entry_fields = []
    for i, (place, name) in enumerate(results):
        place_var = tk.StringVar(value=str(place))
        name_var = tk.StringVar(value=name)
        place_entry = tk.Entry(frame, textvariable=place_var, width=5)
        name_entry = tk.Entry(frame, textvariable=name_var, width=20)
        place_entry.grid(row=i+1, column=0, padx=5, pady=2)
        name_entry.grid(row=i+1, column=1, padx=5, pady=2)
        entry_fields.append((place_var, name_var))

    btn_frame = tk.Frame(window)
    btn_frame.pack(pady=10)

    confirm_btn = tk.Button(btn_frame, text="Confirm", command=on_confirm)
    confirm_btn.pack(side=tk.LEFT, padx=10)

    cancel_btn = tk.Button(btn_frame, text="Cancel", command=on_cancel)
    cancel_btn.pack(side=tk.LEFT, padx=10)

    window.mainloop()
    return updated_results

def save_race_results(results):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    cur.execute('''CREATE TABLE IF NOT EXISTS Players (
        id SERIAL PRIMARY KEY,
        mii_name TEXT UNIQUE,
        elo INTEGER DEFAULT 1000)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS RaceResults (
        id SERIAL PRIMARY KEY,
        player_id INTEGER REFERENCES Players(id),
        placement INTEGER,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    for place, mii in results:
        cur.execute("INSERT INTO Players (mii_name) VALUES (%s) ON CONFLICT (mii_name) DO NOTHING", (mii,))
        cur.execute("SELECT id FROM Players WHERE mii_name = %s", (mii,))
        row = cur.fetchone()
        if row is None:
            print(f"Couldn't find player ID for {mii}")
            continue
        player_id = row[0]
        cur.execute("INSERT INTO RaceResults (player_id, placement) VALUES (%s, %s)", (player_id, int(place)))

    conn.commit()
    conn.close()

    update_elo(results)

# Elo update logic
def update_elo(results):
    results = [(place, mii) for place, mii in results if isinstance(place, int)]
    results.sort(key=lambda x: x[0])

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get current Elo ratings
    elo_data = {}
    for _, mii in results:
        cur.execute("SELECT elo FROM Players WHERE mii_name = %s", (mii,))
        row = cur.fetchone()
        elo_data[mii] = row[0] if row else 1000

    K = 64
    n = len(results)

    for i in range(n):
        mii_i = results[i][1]
        place_i = results[i][0]
        elo_i = elo_data[mii_i]

        actual_score = 0
        expected_score = 0

        for j in range(n):
            if i == j:
                continue

            mii_j = results[j][1]
            place_j = results[j][0]
            elo_j = elo_data[mii_j]

            # Actual score: 1 if beat them, 0 if lost, 0.5 if tied
            if place_i < place_j:
                actual_score += 1
            elif place_i == place_j:
                actual_score += 0.5

            expected_score += 1 / (1 + 10 ** ((elo_j - elo_i) / 400))

        score_diff = actual_score - expected_score
        delta = round(K * score_diff / (n - 1))

        new_elo = elo_i + delta
        cur.execute("UPDATE Players SET elo = %s WHERE mii_name = %s", (new_elo, mii_i))

    conn.commit()
    conn.close()


def get_stats(mii_name):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('''
    SELECT COUNT(*), AVG(placement), MAX(elo)
    FROM RaceResults
    JOIN Players ON RaceResults.player_id = Players.id
    WHERE Players.mii_name = %s
    ''', (mii_name,))
    result = cur.fetchone()
    conn.close()
    return result

# Discord Client
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f"Logged in as {client.user} (ID: {client.user.id})")

    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("❌ Channel not found. Check CHANNEL_ID and bot permissions.")
    else:
        try:
            await channel.send("✅ Bot is ready and can post messages.")
            print("✅ Test message sent.")
        except Exception as e:
            print(f"❌ Failed to send message: {e}")

@client.event
async def on_message(message):
    if message.author.bot:
        return

    if message.content.strip().lower() == "!leaderboard":
        await send_leaderboard(message.channel)

    elif message.content.strip().lower().startswith("!history "):
        parts = message.content.strip().split(maxsplit=1)
        if len(parts) == 2:
            name = parts[1].strip()
            await send_history(message.channel, name)
        else:
            await message.channel.send("Usage: `!history <mii_name>`")

async def post_to_discord(results):
    print("📤 post_to_discord called")
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)

    if not channel:
        print("❌ Channel not found in post_to_discord")
        return

    try:
        stats = []
        for place, name in sorted(results, key=lambda x: x[0]):
            total, avg, elo = get_stats(name) or (0, 0, 1000)
            display_name = f"{name} (bot)" if name not in PLAYERS else name
            stats.append((get_ordinal(place), display_name, total, avg, elo))

        avg_elo = sum(elo for *_, elo in stats) / len(stats) if stats else 0

        header = f"{'Place':<6} {'Name':<25} {'Races':<6} {'Avg':<6} {'Elo':<5}"
        lines = [
            f"Avg Lobby Elo: {avg_elo:.2f}",
            "",
            header,
            "-" * len(header)
        ]
        for ordinal, name, total, avg, elo in stats:
            lines.append(f"{ordinal:<6} {name:<25} {total:<6} {avg:<6.2f} {elo:<5}")

        message = "```markdown\n" + "\n".join(lines) + "\n```"
        await channel.send(message)
        print("✅ Results posted to Discord.")
    except Exception as e:
        print(f"❌ Error posting to Discord: {e}")

# Folder Watcher
class ScreenshotHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(".png"):
            time.sleep(0.5)
            print(f"OCR processing: {event.src_path}")
            results = get_results(event.src_path)
            if not results:
                print("No results parsed.")
                return

            reviewed = review_results_gui(results)
            if reviewed:
                save_race_results(reviewed)
                asyncio.run_coroutine_threadsafe(post_to_discord(reviewed), client.loop)
            else:
                print("Results cancelled.")

def start_watcher():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    observer = Observer()
    observer.schedule(ScreenshotHandler(), SCREENSHOT_DIR, recursive=False)
    observer.start()

# Screenshot Capture
def screenshot_loop():
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)
    def take_screenshot():
        timestamp = int(time.time())
        path = os.path.join(SCREENSHOT_DIR, f"screenshot_{timestamp}.png")
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            mss.tools.to_png(sct_img.rgb, sct_img.size, output=path)
        print(f"Saved screenshot: {path}")
    keyboard.add_hotkey('F8', take_screenshot)
    print("Press F8 to screenshot. ESC to quit.")
    keyboard.wait('esc')
    os._exit(0)

# Main
if __name__ == "__main__":
    threading.Thread(target=screenshot_loop, daemon=True).start()
    start_watcher()
    client.run(BOT_TOKEN)
