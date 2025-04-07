import tkinter as tk
from gui import (
    ClipDownloaderApp,
)  # Import the main application class from the gui package

if __name__ == "__main__":
    root = tk.Tk()
    # Create the application instance, which sets up the GUI
    app = ClipDownloaderApp(root)
    # Start the Tkinter event loop
    root.mainloop()
