"""
   Copyright 2023 Ian Housman

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
"""

#Example of how to utilize the Python GEE task tracking
#This will run a function that will show tasks that are running as well as ready
####################################################################################################
#Import modules
import os,sys
sys.path.append(os.getcwd())

from geeViz.taskManagerLib import *
####################################################################################################
trackTasks()