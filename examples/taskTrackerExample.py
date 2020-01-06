#Example of how to utilize the Python GEE task tracking
#This will run a function that will show tasks that are running as well as ready
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

from geeViz.taskManagerLib import *
####################################################################################################
trackTasks()