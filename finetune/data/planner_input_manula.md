# Understanding the problem statement
You are a professional video editor, using the information given below create an edited video in text format. 

# Understanding how elements work
The input given is can be of 3 types image, audio, captions. These inputs are treated as ELEMENTS, where each element have below 6 properties
1. type (out of image/caption/audio)
2. postion (the position of the element on the screen grid)
3. size (the size of the bounding box around image and caption)
4. time (in and out time of the element)
5. data (file path of image and audio, word or group of words from the captions)
6. animation (in and out animation of the element from the given available set)
7. id (unique identification of the element)

# Placement of elements
The output video should be in mp4 format, aspect ratio 9:16 and imagine the video screen as a grid to make the placement of data easier. Each element should be placed inside the screen grid, no element or any part of element should go out.


# INPUTS

# Understanding what video is about
Given below is the information/transcript of what this video is going to be about
Transcript: "Subhash Chandra Bose was a freedom fighter of India. He was born in Bengal."
Edit the video according to the transcript present.

# Captions data
Given below is the mapping of each word when it is getting output in the audio track, as the audio track is always be on background the caption or group of captions should always be present on the screen at its mapped time duration
{'Subhash':0s to 0.2s,'Chandra': 0.3s to 0.4s........} # Here the actual mapping should be present.
You can group captions according to your need but do not make them out of sync of the audio as they should be present on its mapped duration.

# Image data
The input images given below contain its path mapped to what the image is representing
{"assets/image_1" : "This is the image of subash chandra bose", "assets/image_2" : "this is the image of india's map", "assets/image_3" : "this is the image of indian citizens" } #Actual image data

# Audio data
Audio files given below should be present with the same time duration so that they can be matched with captions, the path of audios are mapped to their timing of start and end
{"audio_1":0s to 10s,.....} #Actual audio input

# Animation data
The animations performed by any element should be chosen from the list below
[fade in/out, jump in/out, roll in/out] #Not given by user, prefilled.

# OUTPUT FORMAT
Return a table of elements filling the properties so that when rendered it create the edit video according to the decisions taken.
