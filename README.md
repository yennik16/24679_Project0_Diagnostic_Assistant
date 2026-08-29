# Automotive Diagnostic Assistant

As the title suggests, this is an automotive diagnostic assistant meant to assist
with vehicle troubleshooting. It allows the user to look up OBD2 trouble codes, as
well as professional Parameter ID (PID) signals which are pulled from the OBDb github page
(https://github.com/OBDb) based on the specific vehicle make, model, and year the 
user inputs. It also features a decision tree which can be used to pinpoint the cause
of an issue, without a code. It allows the user to describe their problem in plain text,
at which point it is able to match the corresponding node in the decision tree to begin
asking additional questions. Several nodes feature simple tests, for which the corresponding
PID is provided. Once a final diagnosis is reached, the user has the option to automatically 
search google for a repair guide.

## How to use it
There are no required dependencies, just install automotive_diagnostic_tool.html and run it
in a browser. The other files are artifacts from previous versions, and were consolidated into
automotive_diagnostic_tool.html

## How the plain text description works

There are 16 symptom categories with written example phrases for each as to what descriptions
of the symptom may look like. A term frequency - inverse document frequency model is built from 
this to figure out which specific words can be used to identify certain categories (weighting words
that concentrate in one category highly, and ones that appear everywhere lowly). The users text 
description is then given the same treatment and compared to each category using cosine similarity. 
These similarities can then be ranked allowing the program to select the top 3 most relevant points
in the decision tree for the user to begin diagnosis at. If an adequate match can not be found, they 
simply start at the top of the tree. The decision tree features questions and tests for the user to 
work through until it works its way to a leaf, containing the final diagnosis.

## Known limitations

The symptom classifier has limited "training" so if the users description differs greatly from the 
training sentences it defaults to the beginning of the tree. The PID to test matching also relies on
word matching, so it can result in false matches if only one or a few words match. The core of the manual
diagnostic tool is still a decision tree, so it is limited in its depth. It is broad and cannot pull specific
information about a model of vehicle to provide more specific and accurate tests/predicted sources of problems.

## AI tool use
I vibecoded this program as discussed in the class. I started on google colab hence the commits here starting 
midway through code devolopment as I had never used github but decided to switch based on lecture/running into issues with the gui.

To start I just used the built in colab AI assistant prompting it with a modified version of my project 0 idea:
make an automotive diagnostic assistant which could be used to predict the cause of car troubles. 
This could help provide a list of things for the user to check themselves, or provide them with a better 
baseline idea of the issue before bringing it to a mechanic. A user will interact with the system by describing 
the issue through a gui and then answering a series of (dynamic) questions, allowing the system to zero in on 
a likely diagnosis. you may need to use a dataset of automotive issues and their causes, a decision tree, a 
model to interpret user answers, and Python to code it.

I then reviewed its output and prompted: 
make a much more in depth decision tree. is there an automotive code database that can be incorporated?

I was not satisfied with the results of this so I found a github database with a list of obd codes myself and 
prompted it to implement https://github.com/obdb

I then prompted it about 10 times with the output of various different tests asking it to continue with a decision 
tree when I felt it stopped with too broad a solution, asked it to implement a feature that would search for online
repair guides when the final issue was found, and fixing various bugs and issues. I also prompted it to start by asking
for a trouble code. I then prompted it to allow for a text description of symptoms rather than relying entirely on generic
buttons. I then prompted it several more times to fix errors, try and improve the depth of diagnosis, and get it to properly 
use the github database I had found. 

I hit a roadblock asking it to create a popout gui rather than one at the bottom of the 
code where it would just compile indefinitely. At this point I switched to claude to further refine it.
I prompted claude to fix the popout gui with notes on what I wanted the flow/appearance to be like. The popout still
would not work however and there was a consistent issue with buttons needing to be clicked multiple times before
text boxes or the next thing would appear. It identified it as a colab issue which is when I switched to github, having it 
generate the initial commit. The rest of the commits also used Claude, limited by its usage limits. I asked it to add the
confidence ranked symptom classification to improve intelligence and prompted it further to improve the decision tree so that
it continued until a single problem was identified, instead of terminating with a short list of possible issues. I also fed it some online decision trees to help guide it. Comments past the fourth commit were written by me, until I realized that the two python scripts
and index.html could be consolidated. At this point, I asked Claude to do so, giving it my commented files to which it added some 
additional comments. The readme was written by me, but seeing as Claude automatically generated one when it recommened the switch to 
github I loosely referenced that.
