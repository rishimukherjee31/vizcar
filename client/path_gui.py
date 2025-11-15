import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import cv2
import numpy as np
import paho.mqtt.client as mqtt
import json

# ------------------------------
# DEFAULT SETTINGS
# ------------------------------

DEFAULT_BROKER = "100.101.214.30"  # Pi's Tailscale IP (change as needed)
DEFAULT_VIDEO  = "http://100.101.214.30:5000/video_feed"

# ------------------------------
# PATH FUNCTIONS IMPORT
# ------------------------------
from path_calculations import path_with_headings, point_path, linear_path, catmull_path, cubic_path, bezier_chained



# ================================================================
#                         PATH GUI CLASS
# ================================================================
class PathGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("VizCar Path Planner")
        self.root.iconbitmap("robot.ico")

        self.points = []
        self.cap = None
        self.stop_flag = False

        # GUI default state variables
        self.method_var = tk.StringVar(value="linear")
        self.broker_var = tk.StringVar(value=DEFAULT_BROKER)
        self.npts_var   = tk.IntVar(value=2)
        self.url_var    = tk.StringVar(value=DEFAULT_VIDEO)

        # ------------------------------
        # CONTROL PANEL
        # ------------------------------
        ctrl = ttk.Frame(root, padding=8)
        ctrl.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(ctrl, text="Video URL:").grid(row=0, column=0)
        url_entry = ttk.Entry(ctrl, textvariable=self.url_var, width=35)
        url_entry.grid(row=0, column=1)

        # Re-open stream when ENTER is pressed
        url_entry.bind("<Return>", lambda e: self.open_video())

        ttk.Label(ctrl, text="Broker:").grid(row=0, column=2)
        ttk.Entry(ctrl, textvariable=self.broker_var, width=15).grid(row=0, column=3)

        ttk.Label(ctrl, text="Method:").grid(row=1, column=0)
        method_box = ttk.Combobox(
            ctrl,
            textvariable=self.method_var,
            values=["linear","catmull","cubic","bezier"],
            width=10,
            state="readonly"
        )
        method_box.grid(row=1, column=1)
        method_box.bind("<<ComboboxSelected>>", self.on_method_change)

        ttk.Label(ctrl, text="#pts/seg:").grid(row=1, column=2)
        ttk.Spinbox(
            ctrl, from_=5, to=500, textvariable=self.npts_var, width=6
        ).grid(row=1, column=3)

        ttk.Button(ctrl, text="Publish", command=self.publish).grid(row=0, column=4, padx=6)
        ttk.Button(ctrl, text="Clear",   command=self.clear).grid(row=1, column=4, padx=6)
        ttk.Button(ctrl, text="Undo", command=self.undo).grid(row=0, column=5, padx=6)

        # Status label
        self.status_var = tk.StringVar(value="Click video to add points. Right-click to undo.")
        ttk.Label(root, textvariable=self.status_var, padding=(6,3)).pack(fill=tk.X)

        # ------------------------------
        # VIDEO FEED WINDOW
        # ------------------------------
        self.video_label = ttk.Label(root)
        self.video_label.pack()

        self.video_label.bind("<Button-1>", self.add_point)
        self.video_label.bind("<Button-3>", self.undo)

        # Start video
        self.open_video()
        self.update_frame()


    def on_method_change(self, event=None):
        method = self.method_var.get()

        # Set defaults for each method
        if method == "linear":
            self.npts_var.set(2)

        else:
            self.npts_var.set(20)

        #self.status_var.set(f"Default #pts/seg set to {self.npts_var.get()} for {method}")

    # ================================================================
    #                        VIDEO HANDLING
    # ================================================================
    def open_video(self):
        """Open video feed using FFMPEG backend."""
        url = self.url_var.get().strip()
        print("[DEBUG] Opening stream:", url)

        # Close previous stream
        if self.cap:
            self.cap.release()

        # Attempt to open the network MJPEG stream
        self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        if not self.cap.isOpened():
            print("[ERROR] Failed to open:", url)
        else:
            print("[SUCCESS] Connected to video stream.")

    def update_frame(self):
        if self.stop_flag:
            return

        if self.cap is None or not self.cap.isOpened():
            self.root.after(20, self.update_frame)
            return

        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.root.after(20, self.update_frame)
            return

        disp = frame.copy()

        # -------------------------------------
        # Draw snapped / smooth path preview
        # -------------------------------------
        path = self.compute_preview_path()
        if path is not None:

            # 1. Draw full polyline
            for i in range(len(path)-1):
                p1 = (int(path[i][0]),   int(path[i][1]))
                p2 = (int(path[i+1][0]), int(path[i+1][1]))
                cv2.line(disp, p1, p2, (0, 255, 255), 2)

            # 2. Draw ONE arrow at the end of the segment
            end1 = (int(path[-2][0]), int(path[-2][1]))
            end2 = (int(path[-1][0]), int(path[-1][1]))
            self.draw_arrow(disp, end1, end2, color=(0,255,255), thickness=2, size=12)

        # -------------------------------------
        # Draw clicked points
        # -------------------------------------
        for (x, y) in self.points:
            cv2.circle(disp, (x, y), 5, (0, 0, 255), -1)

        # Convert to tkinter
        img_rgb = cv2.cvtColor(disp, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)
        imgtk = ImageTk.PhotoImage(img_pil)

        self.video_label.imgtk = imgtk
        self.video_label.configure(image=imgtk)

        self.root.after(20, self.update_frame)



    # ================================================================
    #                       POINT MANAGEMENT
    # ================================================================
    def add_point(self, event):
        """Add click coordinate as a waypoint."""
        x, y = event.x, event.y

        # if self.method_var.get() == "point":
        #     # In point mode, keep only exactly TWO points
        #     if len(self.points) < 2:
        #         self.points.append((x, y))
        #     else:
        #         # Replace second point with the new click
        #         self.points[1] = (x, y)
        # else:
        #     # Other methods accumulate points
        self.points.append((x, y))

        self.status_var.set(f"{len(self.points)} point(s) added.")


    def undo(self, event=None):
        """Remove the last point."""
        if len(self.points) > 0:
            self.points.pop()
            self.status_var.set("Removed last point.")
            self.status_var.set(f"{len(self.points)} point(s) remaining.")
        else:
            self.status_var.set("No points to undo.")
        # self.status_var.set(f"{len(self.points)} point(s) remaining.")


    def clear(self):
        self.points.clear()
        self.status_var.set("Points cleared.")

    def draw_arrow(self, img, p1, p2, color=(0, 255, 0), thickness=2, size=10):
        """
        Draw an arrow from p1 → p2 on an image.
        p1, p2 are (x,y) tuples.
        """
        x1, y1 = p1
        x2, y2 = p2

        # Main line
        cv2.line(img, (x1, y1), (x2, y2), color, thickness)

        # Arrowhead
        angle = np.arctan2(y2 - y1, x2 - x1)

        # Two wings of the arrowhead
        wing1 = (int(x2 - size * np.cos(angle - np.pi/6)),
                int(y2 - size * np.sin(angle - np.pi/6)))

        wing2 = (int(x2 - size * np.cos(angle + np.pi/6)),
                int(y2 - size * np.sin(angle + np.pi/6)))

        cv2.line(img, (x2, y2), wing1, color, thickness)
        cv2.line(img, (x2, y2), wing2, color, thickness)
        
    def compute_preview_path(self):
        """Compute the full preview path using the chosen method."""
        if len(self.points) < 2:
            return None

        method = self.method_var.get()
        npts = self.npts_var.get()

        pts = self.points

        # if method == "point":
        #     path = point_path(pts[0], pts[-1], n=npts)

        if method == "linear":
            path = linear_path(pts, n=npts)

        elif method == "catmull":
            path = catmull_path(pts, n=npts)

        elif method == "cubic":
            path = cubic_path(pts, n=npts)

        elif method == "bezier":
            if len(pts) < 4:
                return None
            # P0, P1, P2, P3 = pts
            path = bezier_chained(pts, n=npts)

        return path

    # ================================================================
    #                       MQTT PUBLISHING
    # ================================================================
    def publish(self):
        """Send path to robot via MQTT."""
        if len(self.points) < 2:
            self.status_var.set("Need at least 2 points!")
            return

        method = self.method_var.get()
        npts = self.npts_var.get()

        # Select path generation
        # if method == "point":
        #     path = point_path(self.points[0], self.points[-1], n=npts)

        if method == "linear":
            path = linear_path(self.points, n=npts)

        elif method == "catmull":
            path = catmull_path(self.points, n=npts)

        elif method == "cubic":
            path = cubic_path(self.points, n=npts)

        elif method == "bezier":
            if len(self.points) < 4:
                self.status_var.set("Bezier needs at least 4 points.")
                return
            path = bezier_chained(self.points, n=npts)

        print("DEBUG #pts/seg =", npts)
        print("DEBUG points list:", self.points)
        print("DEBUG generated path length:", len(path))
        
        # Convert to JSON text
        # payload = json.dumps(path.tolist())
        path_hdg = path_with_headings(path)
        payload = json.dumps({
            "method": method,
            "path": path_hdg
        })

        # Send to MQTT
        broker = self.broker_var.get().strip()
        client = mqtt.Client()
        client.connect(broker, 1883, 60)
        client.publish("robot/path", payload)
        client.disconnect()

        self.status_var.set(f"Path published ({len(path)} pts).")



# ================================================================
#                             MAIN
# ================================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = PathGUI(root)
    root.mainloop()