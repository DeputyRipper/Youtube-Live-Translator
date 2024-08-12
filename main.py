import subprocess
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
import speech_recognition as sr
from googletrans import Translator
import yt_dlp
import threading
import io
from pydub import AudioSegment
from pydub.playback import play

# Get audio stream from YouTube live stream using yt-dlp
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

# Stream and process the audio
def stream_audio_to_text(youtube_url, gui_text_widget, status_label, language_code, playback_toggle):
    while True:
        try:
            stream_url = get_audio_stream(youtube_url)

            ffmpeg_command = [
                'ffmpeg',
                '-i', stream_url,
                '-af', 'volume=2.0',
                '-f', 'wav',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                'pipe:1'
            ]

            ffmpeg_process = subprocess.Popen(ffmpeg_command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            recognizer = sr.Recognizer()
            translator = Translator()

            buffer_size = 16000 * 2 * 15  # 15 seconds of audio
            audio_buffer = io.BytesIO()

            def play_audio(audio_segment):
                play(audio_segment)

            while True:
                try:
                    status_label.config(text="Listening to stream...")

                    raw_audio = ffmpeg_process.stdout.read(buffer_size)
                    if not raw_audio:
                        raise RuntimeError("Stream interrupted")

                    audio_buffer.write(raw_audio)

                    if audio_buffer.tell() >= buffer_size:
                        audio_buffer.seek(0)
                        audio_data = sr.AudioData(audio_buffer.read(), 16000, 2)
                        audio_buffer = io.BytesIO()  # Reset buffer

                        if playback_toggle.get():
                            audio_segment = AudioSegment(data=audio_data.get_wav_data(), sample_width=2, frame_rate=16000, channels=1)
                            play_audio(audio_segment)

                        original_text = recognizer.recognize_google(audio_data, language=language_code)
                        translated_text = translator.translate(original_text, dest='en').text

                        gui_text_widget.config(state=tk.NORMAL)
                        gui_text_widget.insert(tk.END, f"Heard: {original_text}\n")
                        gui_text_widget.insert(tk.END, f"Translated: {translated_text}\n\n")
                        gui_text_widget.config(state=tk.DISABLED)
                        gui_text_widget.yview(tk.END)

                except sr.UnknownValueError:
                    status_label.config(text="Could not understand audio")
                except sr.RequestError as e:
                    status_label.config(text=f"Could not request results; {e}")
                except Exception as e:
                    status_label.config(text=f"An error occurred: {e}")
                    break

        except Exception as e:
            status_label.config(text="Connection lost, attempting to reconnect...")
            continue

# Trigger the start of the process
def start_translation():
    youtube_url = url_entry.get()
    language_code = language_var.get()

    translation_thread = threading.Thread(target=stream_audio_to_text, args=(youtube_url, output_text, status_label, language_code, playback_toggle))
    translation_thread.start()

# Toggle the UI to minimalist mode
def toggle_minimalist_mode():
    if top_frame.winfo_ismapped():
        top_frame.pack_forget()
        status_label.pack_forget()
        root.overrideredirect(True)  # Hide window decorations
        root.config(bg='black')
        output_text.config(bg='black', fg='white', height=20, wrap=tk.WORD)
        root.attributes('-alpha', 0.9)  # Make background semi-transparent

        # Place buttons inside the text box area
        output_text.update_idletasks()  # Make sure layout is updated
        exit_button.place(relx=0.98, rely=0.02, anchor=tk.NE, in_=output_text)
        restore_button.place(relx=0.90, rely=0.02, anchor=tk.NE, in_=output_text)

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
        top_frame.pack(pady=20, fill=tk.X, padx=20)
        status_label.pack(pady=10)
        root.overrideredirect(False)  # Show window decorations
        root.config(bg='#2c2f33')
        output_text.config(bg='#23272a', fg='white', height=15, wrap=tk.WORD)
        root.attributes('-alpha', 1.0)

        # Unbind dragging and resizing actions
        root.unbind('<Button-1>')
        root.unbind('<ButtonRelease-1>')
        root.unbind('<B1-Motion>')

        exit_button.place_forget()
        restore_button.place_forget()

# Close the application
def close_application():
    root.destroy()

# Setup the GUI
root = tk.Tk()
root.title("Live YouTube Translation")
root.geometry("850x550")
root.configure(bg='#2c2f33')

style = ttk.Style()
style.theme_use('clam')
style.configure('TLabel', background='#1e90ff', foreground='white')  # blue background, white text
style.configure('TButton', background='#1e90ff', foreground='white')  #  blue background, white text
style.configure('TCheckbutton', background='#2c2f33', foreground='white')  # White text
style.configure('TEntry', fieldbackground='#23272a', foreground='white', insertcolor='white')  # Darker background, white text
style.configure('TCombobox', fieldbackground='#23272a', background='#23272a', foreground='white')  # Darker background, white text

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
    'es-ES',  # Spanish
    'fr-FR',  # French
    'de-DE',  # German
    'it-IT',  # Italian
    'zh-CN',  # Chinese (Simplified)
    'ja-JP',  # Japanese
    'ko-KR',  # Korean
    'pt-PT',  # Portuguese
    'ar-SA',  # Arabic
], state="readonly")
language_dropdown.set('ru-RU')  # Default to Russian
language_dropdown.pack(side=tk.LEFT, padx=10)

# Start Button
start_button = ttk.Button(top_frame, text="Start Translation", command=start_translation)
start_button.pack(side=tk.LEFT, padx=10)

# Playback Toggle
playback_toggle = tk.BooleanVar()
playback_button = ttk.Checkbutton(root, text="Audio Playback", variable=playback_toggle)
playback_button.pack(pady=10)

# Text Output
output_text = ScrolledText(root, wrap=tk.WORD, height=15, width=70, state=tk.DISABLED, bg='#23272a', fg='white', insertbackground='white')  # White text
output_text.pack(pady=10)

# Status Label
status_label = ttk.Label(root, text="Status: Waiting to start...")
status_label.pack(pady=10)

# Exit and Restore Buttons (initially hidden)
exit_button = ttk.Button(root, text="X", command=close_application)
restore_button = ttk.Button(root, text="Restore UI", command=toggle_minimalist_mode)

# Binding hover event to show/hide the Exit and Restore buttons in minimalist mode only
def show_buttons(event):
    if not top_frame.winfo_ismapped():
        exit_button.place(relx=0.95, rely=0.05, anchor=tk.NE)
        restore_button.place(relx=0.85, rely=0.05, anchor=tk.NE)

def hide_buttons(event):
    if not top_frame.winfo_ismapped():
        exit_button.place_forget()
        restore_button.place_forget()


root.bind('<Enter>', show_buttons)
root.bind('<Leave>', hide_buttons)

# Button to toggle minimalist mode
minimalist_button = ttk.Button(root, text="Minimalist Mode", command=toggle_minimalist_mode)
minimalist_button.pack(pady=5)


root.mainloop()
