# vizcar
This repository contains the materials for creating a modular vision-based piloting system for wheeled robots.

## Installation

First, install the Python dependencies for the web server on the Raspberry Pi (We did this over SSH from a Mac): 

```bash
sudo apt update && sudo apt upgrade -y

sudo apt-get install python3-pip
sudo apt-get install python3-opencv -y
sudo apt-get install python-3-flask

sudo raspi-config  # Enable camera in Interface Options
```


