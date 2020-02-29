# jormungandr_controller
The jormungandr controller is automating all the dirty work a stakepool operator needs to do!

![Image of status update](https://raw.githubusercontent.com/kunoada/Cardano/master/gallery/jormungandr_controller_stat_update.PNG)

## Features
- Starts x amount of nodes
- Based on an invertal of x seconds it will make sure the healthiest node is the leader
- Based on an invertal of x seconds it will print out the status of all nodes 
- Bootstrap stuck check, restart node if it haven't been able to bootstrap for 1000 seconds
- Activate/deactive a stuck check notifier
- Single or multi storages is configurable
- Sendmytip to pooltool from the healthiest node (leader node)
- Failover script, all nodes are elected as leaders for an epoch transition
- Leader check, which makes sure that only one node is leader
- Telegram bot 
    - Notifies when a node is out of sync 
    - Restart command can be executed through bot
    - If any changes in the amount of delegations
    - How many blocks a node is assigned at epoch transition
    - Notifies with a sorted schedule of block times at epoch transition
    - Gives you the simple stats of all nodes

### Dependencies needed;
- PyYAML
- tabulate
- requests
- python-telegram-bot

Can be installed using the requirements file;
```python
pip install -r requirements.txt
```

### Run
Please use the config.json as a template to fill in your required needs. When this is set up correctly, you simply execute the script like

Linux example using python v3:
```python
python3 jor_controller.py
```

Windows example:
```python
py jor_controller.py
```
or
```python
python jor_controller.py
```

It is **recommended** to run the script as a startup service, so the user can fully relax without any need of manual maintenance.

### Telegram Bot

To setup the telegram bot I recommend using this guide; https://medium.com/@mycodingblog/get-telegram-notification-when-python-script-finishes-running-a54f12822cdc

Please fill in the token and chat id in the config file, and set activate to true

### Telegram Bot Usage

  | Command | Description
  | --- | --- |
  | Restart [n] | Restart node n |
  | Stats | Will return an output with the stats of all nodes | 


---------------------
## Step-by-step

- Download jormungandr_controller, either by using 'git clone' or download as a zip.
- Install all needed dependencies; pip install -r requirements.txt
- Rename the file called config.json to my_config.json (to protect against overwriting in case of new git pull)
- Open my_config.json, and type in all information so it fit your setup. (Make sure all comments are removed)
- This tool will only use one stakepool-config file, so based on the number of nodes, it will start each nodes from the port set in the stakepool-config and increment with one per node. ex. Node 0 will use port 3000, Node 1 will use port 3001, etc etc..
- To use the telegram bot, please use the guide linked above at **Telegram Bot** to set up a bot for yourself.
- When the telegram bot is up and running, put in the token and chat id in my_config.json and set "activate" to true.

How to set up a systemd service;

```
sudo nano /etc/systemd/system/jormungandr.service
```
Add this to the file;

```
[Unit]
Description=Shelley Staking Pool

[Service]
Type=simple
Restart=on-failure
RestartSec=5

LimitNOFILE=16384

User=<your user>
Group=users
WorkingDirectory=</path/to/Cardano/jormungandr_controller/>
ExecStart=/usr/bin/python3 -u </path/to/Cardano/jormungandr_controller/jor_controller.py>

[Install]
WantedBy=multi-user.target
```
You have to set up the WorkingDirectory so it fits the paths you have used in my_config.json

Now enable the service, so it start on boot
```
sudo systemctl enable jormungandr.service
```
And start the service to run it right away
```
sudo systemctl start jormungandr.service
```
The outputs can now be followed with
```
journalctl -f -u jormungandr.service
```

To get a nice way of watching the output (adjust 17 to the number of lines that fit your setup)
```
watch -n 1 journalctl -u jormungandr.service -n 17 -o cat
```

## Works on
Tested on both Windows and Linux. If anyone has tried this script on MAC, please let me know! :-)
# OBS 
Python version needs to be 3.6 or higher!
