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

def get_leaderboard():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Only include names in PLAYERS list
    placeholders = ','.join(['%s'] * len(PLAYERS))
    query = f'''
        SELECT Players.mii_name, COUNT(RaceResults.id) AS races, AVG(RaceResults.placement) AS avg_place
        FROM RaceResults
        JOIN Players ON RaceResults.player_id = Players.id
        WHERE Players.mii_name IN ({placeholders})
        GROUP BY Players.mii_name
        ORDER BY avg_place ASC
    '''
    cur.execute(query, PLAYERS)
    leaderboard = cur.fetchall()
    conn.close()
    return leaderboard

def get_history(mii_name, limit=10):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('''
        SELECT placement, timestamp
        FROM RaceResults
        JOIN Players ON RaceResults.player_id = Players.id
        WHERE Players.mii_name = %s
        ORDER BY RaceResults.timestamp DESC
        LIMIT %s
    ''', (mii_name, limit))
    results = cur.fetchall()
    conn.close()
    return results

def get_results(screenshot):
    parsed_results = []
    raw = reader.readtext(screenshot, detail=0)
    first_match_found = False
    # print(raw)
    for idx, name in enumerate(raw):
        if name in PLAYERS:
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

    # print(parsed_results)
    return parsed_results

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
        mii_name TEXT UNIQUE)''')
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

def get_stats(mii_name):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    cur.execute('''
        SELECT COUNT(*), AVG(placement)
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
async def on_message(message):
    if message.author.bot:
        return

    if message.content.strip().lower() == '!leaderboard':
        leaderboard = get_leaderboard()
        if not leaderboard:
            await message.channel.send("No race data available.")
            return

        msg = "**🏁 Leaderboard — Average Placement**\n"
        msg += "```plaintext\n"
        msg += f"{'Rank':<5} {'Player':<20} {'Races':<7} {'Avg':<5}\n"
        msg += "-" * 42 + "\n"
        for i, (name, count, avg) in enumerate(leaderboard, start=1):
            msg += f"{i:<5} {name:<20} {count:<7} {avg:.2f}\n"
        msg += "```"
        await message.channel.send(msg)

    if message.content.lower().startswith('!history '):
        parts = message.content.split(maxsplit=1)
        if len(parts) < 2:
            await message.channel.send("Usage: `!history <player_name>`")
            return

        name = parts[1].strip()
        if name not in PLAYERS:
            await message.channel.send(f"Player `{name}` not found.")
            return

        history = get_history(name)
        if not history:
            await message.channel.send(f"No history found for **{name}**.")
            return

        msg = f"**📜 Placement History for `{name}`**\n"
        msg += "```plaintext\n"
        msg += f"{'Place':<8} {'Date':<16} {'Time':<6}\n"
        msg += "-" * 32 + "\n"
        for place, ts in history:
            date_str = ts.strftime('%Y-%m-%d')
            time_str = ts.strftime('%H:%M')
            msg += f"{get_ordinal(place):<8} {date_str:<16} {time_str:<6}\n"
        msg += "```"
        await message.channel.send(msg)

async def post_to_discord(results):
    await client.wait_until_ready()
    channel = client.get_channel(CHANNEL_ID)
    if not channel:
        print("Channel not found.")
        return
    msg = "**Cup Results:**\n"
    for place, name in results:
        total, avg = get_stats(name) or (0, 0)  # handle None
        ordinal_place = get_ordinal(place)
        avg = avg if avg else 0
        msg += f"{ordinal_place}: {name} — {total} cups, avg place: {avg:.2f}\n"
    await channel.send(msg)

# Folder Watcher
class ScreenshotHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(".png"):
            time.sleep(0.5)
            print(f"OCR processing: {event.src_path}")
            results = get_results(event.src_path)
            if not results:
                print("❌ No results parsed.")
                return

            reviewed = review_results_gui(results)
            if reviewed:
                save_race_results(reviewed)
                asyncio.run_coroutine_threadsafe(post_to_discord(reviewed), client.loop)
            else:
                print("❌ Results cancelled.")

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
    print("Press F8 to screenshot.")
    # Removed wait for ESC, so script keeps running
    while True:
        time.sleep(1)

# Main
if __name__ == "__main__":
    threading.Thread(target=screenshot_loop, daemon=True).start()
    start_watcher()
    client.run(BOT_TOKEN)
