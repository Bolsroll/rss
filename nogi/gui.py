import tkinter as tk
from tkinter import messagebox
import json
import os
import sys
import threading

# --------------------------
# 実行ディレクトリ固定
# --------------------------
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

os.chdir(BASE_DIR)

# --------------------------
# Playwrightパス固定
# --------------------------
# os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")


# --------------------------
# 設定 読み込み
# --------------------------
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass

    return {
        "member_id": "48008",
        "start_page": "1",
        "end_page": "3"
    }


# --------------------------
# 設定 保存
# --------------------------
def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("config保存失敗:", e)


# --------------------------
# 実行処理
# --------------------------
def run_script():
    member_id = entry_member.get()
    start_page = entry_start.get()
    end_page = entry_end.get()

    if not member_id or not start_page.isdigit() or not end_page.isdigit():
        messagebox.showerror("エラー", "入力値が不正です")
        return

    save_config({
        "member_id": member_id,
        "start_page": start_page,
        "end_page": end_page
    })

    btn_run.config(state="disabled", text="Running...")

    def task():
        try:
            import asyncio
            from archive_to_xml_auto import main

            asyncio.run(main(member_id, int(start_page), int(end_page)))

            # UIスレッドで実行
            root.after(0, lambda: messagebox.showinfo("完了", "処理が完了しました"))

        except Exception as e:
            # ★ここ修正（lambdaスコープ問題回避）
            err = str(e)
            root.after(0, lambda err=err: messagebox.showerror("エラー", err))

        finally:
            root.after(0, lambda: btn_run.config(state="normal", text="Run"))

    threading.Thread(target=task, daemon=True).start()


# --------------------------
# ウィンドウ閉じた時に完全終了
# --------------------------
def on_close():
    try:
        root.destroy()
    finally:
        os._exit(0)  # ← ターミナルごと強制終了


# --------------------------
# GUI
# --------------------------
root = tk.Tk()
root.title("Nogizaka Archive Tool")
root.geometry("300x220")

config = load_config()

tk.Label(root, text="Member ID").pack()
entry_member = tk.Entry(root)
entry_member.insert(0, config["member_id"])
entry_member.pack()

tk.Label(root, text="Start Page").pack()
entry_start = tk.Entry(root)
entry_start.insert(0, config["start_page"])
entry_start.pack()

tk.Label(root, text="End Page").pack()
entry_end = tk.Entry(root)
entry_end.insert(0, config["end_page"])
entry_end.pack()

btn_run = tk.Button(root, text="Run", command=run_script)
btn_run.pack(pady=15)

# 閉じる処理
root.protocol("WM_DELETE_WINDOW", on_close)

root.mainloop()
