# jormungandr_controller
The jormungandr controller is automating all the dirty work a stakepool operator needs to do!

## Features
- Starts x amount of nodes
- Based on a invertal of x seconds it will make sure the healthiest node is the leader
- Based on a invertal of x seconds it will print out the status of all nodes 
![Image of status update](jormungandr_controller/jormungandr_controller_stat_update.PNG)

### Dependencies needed;
- PyYAML
- tabulate

---------------------

## Works on
Tested on both Windows and Linux. If anyone has tried this script on MAC, please let me know! :-)
# OBS 
When using this script, it is important to configure the variables inside the script which is marked as CONFIGURATION!
