"""
A module for manipulating audio files and their associated Echo Nest
Analyze API analyses.

AudioData, audiosettingsfromffmpeg, and getpieces by Robert Ochshorn
on 2008-06-06.  Some refactoring and everything else by Joshua Lifton
2008-09-07.  Much refactoring remains.
"""

__version__ = "$Revision: 0 $"
# $Source$

import commands, os, struct, tempfile, wave,md5
import numpy
import echonest.web.analyze as analyze;


class AudioAnalysis(object) :
    """
    This class wraps echonest.web to allow transparent caching of the
    audio analysis of an audio file.

    For example, the following script will display the bars of a track
    twice:
    
        from echonest import *
        a = audio.AudioAnalysis('YOUR_TRACK_ID_HERE')
        a.bars
        a.bars

    The first time a.bars is called, a network request is made of the
    Echo Nest anaylze API.  The second time time a.bars is called, the
    cached value is returned immediately.

    An AudioAnalysis object can be created using an existing ID, as in
    the example above, or by specifying the audio file to upload in
    order to create the ID, as in:

        a = audio.AudioAnalysis(filename='FULL_PATH_TO_AUDIO_FILE')
    """

    # Any variable in this listing is fetched over the network once
    # and then cached.  Calling refreshCachedVariables will force a
    # refresh.
    CACHED_VARIABLES = ( 'bars', 
                         'beats', 
                         'duration', 
                         'end_of_fade_in', 
                         'key',
                         'loudness',
                         'metadata',
                         'mode',
                         'sections',
                         'segments',
                         'start_of_fade_out',
                         'tatums',
                         'tempo',
                         'time_signature' )

    def __init__( self, audio, parsers=None ) :
        """
        Constructor.  If the arugment is a valid local path or a URL,
        the track ID is generated by uploading the file to the Echo
        Nest Analyze API.  Otherwise, the argument is assumed to be
        the track ID.

        @param audio A string representing either a path to a local
        file, a valid URL, or the ID of a file that has already been
        uploaded for analysis.

        @param parsers A dictionary of keys consisting of cached
        variable names and values consisting of functions to be used
        to parse those variables as they are cached.  No parsing is
        done for variables without parsing functions or if the parsers
        argument is None.
        """

        if parsers is None :
            parsers = {}
        self.parsers = parsers

        if type(audio) is not str :
            # Argument is invalid.
            raise TypeError("Argument 'audio' must be a string representing either a filename, track ID, or MD5.")
        elif os.path.isfile(audio) or '.' in audio :
            # Argument is either a filename or URL.
            doc = analyze.upload(audio)
            self.id = doc.getElementsByTagName('thingID')[0].firstChild.data
        else:
            # Argument is a md5 or track ID.
            self.id = audio
            

        # Initialize cached variables to None.
        for cachedVar in AudioAnalysis.CACHED_VARIABLES : 
            self.__setattr__(cachedVar, None)



    def refreshCachedVariables( self ) :
        """
        Forces all cached variables to be updated over the network.
        """
        for cachedVar in AudioAnalysis.CACHED_VARIABLES : 
            self.__setattr__(cachedVar, None)
            self.__getattribute__(cachedVar)



    def __getattribute__( self, name ) :
        """
        This function has been modified to support caching of
        variables retrieved over the network.
        """
        if name in AudioAnalysis.CACHED_VARIABLES :
            if object.__getattribute__(self, name) is None :
                getter = analyze.__dict__[ 'get_' + name ]
                value = getter(object.__getattribute__(self, 'id'))
                parseFunction = object.__getattribute__(self, 'parsers').get(name)
                if parseFunction :
                    value = parseFunction(value)
                self.__setattr__(name, value)
        return object.__getattribute__(self, name)





class AudioData(object):

    # XXX : This init function needs to be heavily refactored.
    def __init__(self, filename=None, ndarray=None, shape=None, sampleRate=None, numChannels=None):
                
        # Fold in old load() function.
        if (filename is not None) and (ndarray is None) :
            if sampleRate is None or numChannels is None:
                #force sampleRate and num numChannels to 44100 hz, 2
                sampleRate, numChannels = 44100, 2
                foo, fileToRead = tempfile.mkstemp(".wav")                
                cmd = "ffmpeg -y -i \""+filename+"\" -ar "+str(sampleRate)+" -ac "+str(numChannels)+" "+fileToRead
                #print cmd
                parsestring = commands.getstatusoutput(cmd)
                parsestring = commands.getstatusoutput("ffmpeg -i "+fileToRead)
                sampleRate, numChannels = audiosettingsfromffmpeg(parsestring[1])
            else :
                fileToRead = filename

            w = wave.open(fileToRead, 'r')
            numFrames = w.getnframes()
            raw = w.readframes(numFrames)
            sampleSize = numFrames*numChannels
            data = numpy.array(map(int,struct.unpack("%sh" %sampleSize,raw)), numpy.int16)
            ndarray = numpy.array(data, dtype=numpy.int16)
            if numChannels == 2:
                ndarray = numpy.reshape(ndarray, (numFrames, 2))

        # Continue with the old __init__() function
        self.filename = filename
        self.sampleRate = sampleRate
        self.numChannels = numChannels
        
        if shape is None and isinstance(ndarray, numpy.ndarray):
            self.data = numpy.zeros(ndarray.shape, dtype=numpy.int16)
        elif shape is not None:
            self.data = numpy.zeros(shape, dtype=numpy.int16)
        else:
            self.data = None
        self.endindex = 0
        if ndarray is not None:
            self.endindex = len(ndarray)
            self.data[0:self.endindex] = ndarray



    def __getitem__(self, index):
        "returns individual frame or the entire slice as an AudioData"
        if isinstance(index, float):
            index = int(index*self.sampleRate)
        elif hasattr(index, "start") and hasattr(index, "duration"):
            index =  slice(index.start, index.start+index.duration)

        if isinstance(index, slice):
            if ( hasattr(index.start, "start") and 
                 hasattr(index.stop, "duration") and 
                 hasattr(index.stop, "start") ) :
                index = slice(index.start.start, index.stop.start+index.stop.duration)

        if isinstance(index, slice):
            return self.getslice(index)
        else:
            return self.getsample(index)



    def getslice(self, index):
        if isinstance(index.start, float):
            index = slice(int(index.start*self.sampleRate), int(index.stop*self.sampleRate), index.step)
        return AudioData(None, self.data[index],sampleRate=self.sampleRate)



    def getsample(self, index):
        if isinstance(index, int):
            return self.data[index]
        else:
            #let the numpy array interface be clever
            return AudioData(None, self.data[index])



    def __add__(self, as2):
        if self.data is None:
            return AudioData(None, as2.data.copy())
        elif as2.data is None:
            return AudioData(None, self.data.copy())
        else:
            return AudioData(None, numpy.concatenate((self.data,as2.data)))



    def append(self, as2):
        "add as2 at the endpos of this AudioData"
        self.data[self.endindex:self.endindex+len(as2)] = as2.data[0:]
        self.endindex += len(as2)



    def __len__(self):
        if self.data is not None:
            return len(self.data)
        else:
            return 0



    def save(self, filename=None):
        "save sound to a wave file"

        if filename is None:
            foo,filename = tempfile.mkstemp(".wav")

        ###BASED ON SCIPY SVN (http://projects.scipy.org/pipermail/scipy-svn/2007-August/001189.html)###
        fid = open(filename, 'wb')
        fid.write('RIFF')
        fid.write('\x00\x00\x00\x00')
        fid.write('WAVE')
        # fmt chunk
        fid.write('fmt ')
        if self.data.ndim == 1:
            noc = 1
        else:
            noc = self.data.shape[1]
        bits = self.data.dtype.itemsize * 8
        sbytes = self.sampleRate*(bits / 8)*noc
        ba = noc * (bits / 8)
        fid.write(struct.pack('lhHLLHH', 16, 1, noc, self.sampleRate, sbytes, ba, bits))
        # data chunk
        fid.write('data')
        fid.write(struct.pack('l', self.data.nbytes))
        self.data.tofile(fid)
        # Determine file size and place it in correct
        #  position at start of the file. 
        size = fid.tell()
        fid.seek(4)
        fid.write(struct.pack('l', size-8))
        fid.close()

        return filename



def audiosettingsfromffmpeg(parsestring):
    parse = parsestring.split('\n')
    freq, chans = 44100, 2
    for line in parse:
        if "Stream #0" in line and "Audio" in line:
            segs = line.split(", ")
            for s in segs:
                if "Hz" in s:
                    #print "Found: "+str(s.split(" ")[0])+"Hz"
                    freq = int(s.split(" ")[0])
                elif "stereo" in s:
                    #print "stereo"
                    chans = 2
                elif "mono" in s:
                    #print "mono"
                    chans = 1

    return freq, chans



def getpieces(audioData, segs):
    "assembles a list of segments into one AudioData"
    #calculate length of new segment
    dur = 0
    for s in segs:
        dur += int(s.duration*audioData.sampleRate)

    dur += 100000 #another two seconds just for goodwill...

    #determine shape of new array
    if len(audioData.data.shape) > 1:
        newshape = (dur, audioData.data.shape[1])
        newchans = audioData.data.shape[1]
    else:
        newshape = (dur,)
        newchans = 1

    #make accumulator segment
    newAD = AudioData(shape=newshape,sampleRate=audioData.sampleRate, numChannels=newchans)

    #concatenate segs to the new segment
    for s in segs:
        newAD.append(audioData[s])

    return newAD



class AudioFile(AudioData) :
    def __init__(self, filename) :
        parsers = { 'bars' : barsParser, 
                    'beats' : beatsParser,
                    'sections' : sectionsParser,
                    'segments' : fullSegmentsParser,
                    'tatums' : tatumsParser,
                    'metadata' : metadataParser,
                    'tempo' : globalParserFloat,
                    'duration' : globalParserFloat,
                    'loudness' : globalParserFloat,
                    'end_of_fade_in' : globalParserFloat,
                    'start_of_fade_out' : globalParserFloat,
                    'key' : globalParserInt,
                    'mode' : globalParserInt,
                    'time_signature' : globalParserInt,
                    }
        AudioData.__init__(self, filename=filename)
        self.analysis = AudioAnalysis(filename, parsers)



class ExistingTrack():
    def __init__(self, trackID_or_Filename):
        parsers = { 'bars' : barsParser, 
                    'beats' : beatsParser,
                    'sections' : sectionsParser,
                    'segments' : fullSegmentsParser,
                    'tatums' : tatumsParser,
                    'metadata' : metadataParser,
                    'tempo' : globalParserFloat,
                    'duration' : globalParserFloat,
                    'loudness' : globalParserFloat,
                    'end_of_fade_in' : globalParserFloat,
                    'start_of_fade_out' : globalParserFloat,
                    'key' : globalParserInt,
                    'mode' : globalParserInt,
                    'time_signature' : globalParserInt,
                    }
        if(os.path.isfile(trackID_or_Filename)):
            trackID = md5.new(file(trackID_or_Filename).read()).hexdigest()
            print "Computed MD5 of file is " + trackID
        else:
            trackID = trackID_or_Filename
        self.analysis = AudioAnalysis(trackID, parsers)



class AudioQuantum(object) :
    def __init__(self, start=0, duration=0) :
        self.start = start
        self.duration = duration


class AudioSegment(AudioQuantum):
    'For those who want feature-rich segments'
    # Not sure I like the stupid number of arguments in the init 
    #  function, but it's a one-off for now.
    def __init__(self, start=0., duration=0., pitches=[], timbre=[], 
                 loudness_begin=0., loudness_max=0., time_loudness_max=0.):
        self.start = start
        self.duration = duration
        self.pitches = pitches
        self.timbre = timbre
        self.loudness_begin = loudness_begin
        self.loudness_max = loudness_max
        self.time_loudness_max = time_loudness_max

class AudioQuantumList(list):
    "container that enables content-based selection"
    def that(self, filt):
        out = AudioQuantumList()
        out.extend(filter(None, map(filt, self)))
        return out



def dataParser(tag, doc) :
    out = AudioQuantumList()
    nodes = doc.getElementsByTagName(tag)
    for n in nodes :
        out.append( AudioQuantum(float(n.firstChild.data)) )
    for i in range(len(out) - 1) :
        out[i].duration = out[i+1].start - out[i].start
    out[-1].duration = out[-2].duration
    return out



def attributeParser(tag, doc) :
    out = AudioQuantumList()
    nodes = doc.getElementsByTagName(tag)
    for n in nodes :
        out.append( AudioQuantum(float(n.getAttribute('start')),
                                 float(n.getAttribute('duration'))) )
    return out



def globalParserFloat(doc) :
    d = doc.firstChild.childNodes[4].childNodes[0]
    if d.getAttributeNode('confidence'):
        return float(d.childNodes[0].data), float(d.getAttributeNode('confidence').value)
    else:
        return float(d.childNodes[0].data)



def globalParserInt(doc) :
    d = doc.firstChild.childNodes[4].childNodes[0]
    if d.getAttributeNode('confidence'):
        return int(d.childNodes[0].data), float(d.getAttributeNode('confidence').value)
    else:
        return int(d.childNodes[0].data)



def barsParser(doc) :
    return dataParser('bar', doc)



def beatsParser(doc) :
    return dataParser('beat', doc)
   


def tatumsParser(doc) :
    return dataParser('tatum', doc)



def sectionsParser(doc) :
    return attributeParser('section', doc)



def segmentsParser(doc) :
    return attributeParser('segment', doc)



def metadataParser(doc) :
    out = {}
    for node in doc.firstChild.childNodes[4].childNodes:
        out[node.nodeName] = node.firstChild.data
    return out



def fullSegmentsParser(doc):
    out = AudioQuantumList()
    nodes = doc.getElementsByTagName('segment')
    for n in nodes:
        start = float(n.getAttribute('start'))
        duration = float(n.getAttribute('duration'))
        
        loudnessnodes = n.getElementsByTagName('dB')
        for l in loudnessnodes:
            if l.hasAttribute('type'):
                time_loudness_max = float(l.getAttribute('time'))
                loudness_max = float(l.firstChild.data)
            else:
                loudness_begin = float(l.firstChild.data)
        
        pitchnodes = n.getElementsByTagName('pitch')
        pitches=[]
        for p in pitchnodes:
            pitches.append(float(p.firstChild.data))
        
        timbrenodes = n.getElementsByTagName('coeff')
        timbre=[]
        for t in timbrenodes:
            timbre.append(float(t.firstChild.data))
        
        out.append(AudioSegment(start=start, duration=duration, pitches=pitches, 
                        timbre=timbre, loudness_begin=loudness_begin, 
                        loudness_max=loudness_max, time_loudness_max=time_loudness_max))
    return out
