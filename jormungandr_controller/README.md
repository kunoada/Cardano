# jormungandr_controller
The jormungandr controller is automating all the dirty work a stakepool operator needs to do!

## Features
- Starts x amount of nodes
- Based on an invertal of x seconds it will make sure the healthiest node is the leader
- Based on an invertal of x seconds it will print out the status of all nodes 

![Image of status update](https://raw.githubusercontent.com/kunoada/Cardano/master/jormungandr_controller/jormungandr_controller_stat_update.PNG)

- Stuck check, restart node if it haven't been able to bootstrap for 1000 seconds
- Sendmytip to pooltool from the healthiest node (leader node)
- Failover script, all nodes are elected as leaders for an epoch transition
- Leader check, which makes sure that only one node is leader, while having blocks
- Telegram bot notifies when a node is out of sync, also a restart command can be executed

### Dependencies needed;
- PyYAML
- tabulate
- requests
- python-telegram-bot

Can be installed using the requirements file;
```python
pip install -r requirements.txt
```

### Setup
Please use the config.json as a template to fill in your required needs. When this is set up correctly, you simply execute the script like

Linux example using python v3.6:
```python
python3.6 jormungandr_controller.py
```

Windows example:
```python
py jormungandr_controller.py
```
or
```python
python jormungandr_controller.py
```

It is **recommended** to run the script as a startup service, so the user can fully relax without any need of manual maintenance.

#### Telegram Bot

To setup the telegram bot I recommend using this guide; https://medium.com/@mycodingblog/get-telegram-notification-when-python-script-finishes-running-a54f12822cdc

Please fill in the token and chat id in the config file

#### Telegram Bot Usage

**Actions**

  Restart node; text the bot 'restart x', where x can be any number between node 0...n
  
  Example; restart 1

---------------------

## Works on
Tested on both Windows and Linux. If anyone has tried this script on MAC, please let me know! :-)
# OBS 
When using this script, it is important to configure the variables inside the config file!
