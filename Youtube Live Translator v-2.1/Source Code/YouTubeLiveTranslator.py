import os
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
import threading
from vosk import Model, KaldiRecognizer
import json
import sys
import time
import subprocess
import yt_dlp
import logging
import argostranslate.package
import argostranslate.translate

# Set up logging
logging.basicConfig(filename='LiveTranslator.log', filemode='w', level=logging.DEBUG)
logging.debug("Starting application...")

# Global variables
stop_translation_flag = False
ffmpeg_process = None

# Get the path to the directory where the script is located
if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)

    lib_path = os.path.join(application_path, 'lib')
    torch_lib_path = os.path.join(application_path, 'lib', 'torch', 'lib')
    os.environ['PATH'] = lib_path + os.pathsep + torch_lib_path + os.pathsep + os.environ['PATH']
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

# Function to install the Russian-to-English model from a local file
def install_ru_en_model():
    models_dir = os.path.join(application_path, 'models')

    # Ensure the models directory exists
    if not os.path.exists(models_dir):
        os.makedirs(models_dir)

    # Path to the Russian-to-English model file
    model_file = os.path.join(models_dir, 'translate-ru_en.argosmodel')

    if os.path.exists(model_file):
        # Install the model from the local file
        argostranslate.package.install_from_path(model_file)
        print("Russian-to-English model installed from local file.")
    else:
        print("Error: Russian-to-English model file not found.")
        sys.exit(1)  # Exit the program if the model file is not found


# Install the translation model at launch
install_ru_en_model()

# Path to the icon file
icon_path = os.path.join(application_path, "Logo.ico")

# Initialize Vosk model for speech recognition
model_path = os.path.join(application_path, "model")
model = Model(model_path)

# Grabs the audio from the url
def get_audio_stream(youtube_url):
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'force_generic_extractor': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(youtube_url, download=False)
        formats = info_dict.get('formats', None)
        for f in formats:
            if f.get('acodec') != 'none':  # Ensuring it's an audio format
                return f['url']

# Function to translate text
def translate_text(text, target_language='en'):
    if not text.strip():
        return None  # Skip translation if there's no text

    try:
        # Perform translation using Argos Translate
        translated_text = argostranslate.translate.translate(text, 'ru', target_language)
        return translated_text
    except Exception as e:
        logging.error(f"Translation Error: {e}")
        return f"Translation Error: {e}"

# Function that uses speach recognition to turn audio to text
def stream_audio_to_text(youtube_url, gui_text_widget, status_label, language_code):
    global stop_translation_flag, ffmpeg_process
    stop_translation_flag = False  # Reset stop flag
    retry_count = 0
    max_retries = 5

    # Calls upon the function to get the audio
    def start_ffmpeg_process():
        global ffmpeg_process
        stream_url = get_audio_stream(youtube_url)
        print(f"Stream URL: {stream_url}")

        # post processesing on audio, so it can be better recognized.
        ffmpeg_command = [
            'ffmpeg',
            '-i', stream_url,
            '-af', 'volume=1.5,acompressor,aresample=16000',
            '-f', 'wav',
            '-acodec', 'pcm_s16le',
            '-ar', '16000',
            '-ac', '1',
            'pipe:1'
        ]
        print(f"Running ffmpeg command: {' '.join(ffmpeg_command)}")
        ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Print any ffmpeg errors
        def log_ffmpeg_errors():
            while True:
                error = ffmpeg_process.stderr.readline().decode()
                if "error" in error.lower():  # Only log actual errors
                    print(f"ffmpeg error: {error.strip()}")
                if "I/O error" in error:  # Specific check for I/O error
                    print("ffmpeg encountered an I/O error. Restarting...")
                    restart_ffmpeg_process()
                if not error and ffmpeg_process.poll() is not None:
                    break

        threading.Thread(target=log_ffmpeg_errors, daemon=True).start()

 # Error handling to regrab a dropped connection
    def restart_ffmpeg_process():
        nonlocal retry_count
        if retry_count < max_retries:
            retry_count += 1
            print(f"Attempting to restart ffmpeg process. Retry {retry_count}/{max_retries}")
            status_label.config(text=f"Status: Error occurred, retrying {retry_count}/{max_retries}...")
            start_ffmpeg_process()
        else:
            print("Max retries reached. Stopping translation.")
            status_label.config(text="Status: Error - Translation stopped after max retries.")
            stop_translation()

    def update_status_translating():
        status_label.config(text="Status: Translating...")

    start_ffmpeg_process()

    recognizer = KaldiRecognizer(model, 16000)
    recognizer.SetWords(True)

    last_activity_time = time.time()  # Track last time something was recognized

    while True:
        if stop_translation_flag:
            print("Terminating ffmpeg process...")
            ffmpeg_process.terminate()  # Terminate ffmpeg process
            break

        data = ffmpeg_process.stdout.read(4096)
        if recognizer.AcceptWaveform(data):
            update_status_translating()  # Update status to show translation is ongoing
            result = recognizer.Result()
        else:
            result = recognizer.PartialResult()  # Handle partial results

        result_dict = json.loads(result)
        recognized_text = result_dict.get('text', '')

        if recognized_text:
            last_activity_time = time.time()  # Reset inactivity timer

            translated_text = translate_text(recognized_text.strip(), target_language='en')

            # Display real-time translation in the GUI if translation is successful
            if translated_text:
                gui_text_widget.config(state=tk.NORMAL)
                gui_text_widget.insert(tk.END, f"Recognized: {recognized_text}\n")
                gui_text_widget.insert(tk.END, f"Translated: {translated_text}\n\n")
                gui_text_widget.config(state=tk.DISABLED)
                gui_text_widget.yview(tk.END)
        else:
            current_time = time.time()
            if current_time - last_activity_time > 300:  # 5 minutes of inactivity
                gui_text_widget.config(state=tk.NORMAL)
                gui_text_widget.insert(tk.END, "No speech detected for 5 minutes...\n")
                gui_text_widget.config(state=tk.DISABLED)
                gui_text_widget.yview(tk.END)
                last_activity_time = current_time

# Function to begin translation when start_translation button is pressed
def start_translation():
    youtube_url = url_entry.get()
    language_code = language_var.get()
    status_label.config(text="Status: Translating...")
    translation_thread = threading.Thread(target=stream_audio_to_text,
                                          args=(youtube_url, output_text, status_label, language_code))
    translation_thread.start()

# Function to stop translation when start_translation button is pressed
def stop_translation():
    global stop_translation_flag, ffmpeg_process
    stop_translation_flag = True
    status_label.config(text="Status: Stopped.")
    if ffmpeg_process:
        print("Stopping ffmpeg process...")
        ffmpeg_process.terminate()
        ffmpeg_process = None

# Function to setup minimalist mode gui
def toggle_minimalist_mode():
    if top_frame.winfo_ismapped():
        # Hide top frame and status label
        top_frame.pack_forget()
        status_label.pack_forget()

        # Resize the window to show only the text box and minimalist button
        root.geometry("800x250")
        root.overrideredirect(True)  # Hide the title bar
        root.config(bg='black')
        output_text.config(bg='black', fg='white', height=10, wrap=tk.WORD)
        root.attributes('-alpha', 0.9)  # Make background semi-transparent

        # Allow window dragging without title bar
        def start_move(event):
            root.x = event.x
            root.y = event.y

        def stop_move(event):
            root.x = None
            root.y = None

        def on_motion(event):
            x = (event.x_root - root.x)
            y = (event.y_root - root.y)
            root.geometry(f"+{x}+{y}")

        root.bind('<Button-1>', start_move)
        root.bind('<ButtonRelease-1>', stop_move)
        root.bind('<B1-Motion>', on_motion)

    else:
        # Restore UI components and window size
        top_frame.pack(pady=20, fill=tk.X, padx=20)
        status_label.pack(pady=10)
        root.geometry("850x550")
        root.overrideredirect(False)  # Show the title bar
        root.config(bg='#2c2f33')
        output_text.config(bg='#23272a', fg='white', height=15, wrap=tk.WORD)
        root.attributes('-alpha', 1.0)

        # Unbind dragging and resizing actions
        root.unbind('<Button-1>')
        root.unbind('<ButtonRelease-1>')
        root.unbind('<B1-Motion>')

# Close the application
def close_application():
    global stop_translation_flag, ffmpeg_process
    stop_translation_flag = True
    if ffmpeg_process:
        print("Closing application and stopping ffmpeg process...")
        ffmpeg_process.terminate()
    root.destroy()

# Setup the GUI
root = tk.Tk()
root.title("Live YouTube Translation")
root.geometry("850x550")
root.configure(bg='#2c2f33')

# Set the window icon
if os.path.exists(icon_path):
    root.iconbitmap(icon_path)

style = ttk.Style()
style.theme_use('clam')
style.configure('TLabel', background='#1e90ff', foreground='white')
style.configure('TButton', background='#1e90ff', foreground='white')
style.configure('TCheckbutton', background='#2c2f33', foreground='white')
style.configure('TEntry', fieldbackground='#23272a', foreground='white',
                insertcolor='white')
style.configure('TCombobox', fieldbackground='#23272a', background='#23272a',
                foreground='white')

top_frame = ttk.Frame(root, style='TLabel')
top_frame.pack(pady=20, fill=tk.X, padx=20)

# URL Entry
url_label = ttk.Label(top_frame, text="YouTube URL:")
url_label.pack(side=tk.LEFT, padx=5)

url_entry = ttk.Entry(top_frame, width=50)
url_entry.pack(side=tk.LEFT, padx=10)

# Language Dropdown
language_label = ttk.Label(top_frame, text="Language:")
language_label.pack(side=tk.LEFT, padx=5)

language_var = tk.StringVar()
language_dropdown = ttk.Combobox(top_frame, textvariable=language_var, values=[
    'ru-RU',  # Russian
], state="readonly")
language_dropdown.set('ru-RU')  # Default to Russian
language_dropdown.pack(side=tk.LEFT, padx=10)

# Start Button
start_button = ttk.Button(top_frame, text="Start Translation", command=start_translation)
start_button.pack(side=tk.LEFT, padx=10)

# Stop Button
stop_button = ttk.Button(top_frame, text="Stop Translation", command=stop_translation)
stop_button.pack(side=tk.LEFT, padx=10)

# Text Output
output_text = ScrolledText(root, wrap=tk.WORD, height=15, width=70, state=tk.DISABLED, bg='#23272a', fg='white',
                           insertbackground='white')
output_text.pack(pady=10)

# Status Label
status_label = ttk.Label(root, text="Status: Waiting to start...")
status_label.pack(pady=10)

# Button to toggle minimalist mode
minimalist_button = ttk.Button(root, text="Minimalist Mode", command=toggle_minimalist_mode)
minimalist_button.pack(pady=5)

root.mainloop()
