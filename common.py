'''
Common
- For importing only
- Common operations and variables for interactive interpreter and scripts
- Recommended use: `from common import *`
- 17-06-18 - upgraded JSON ops to use jsonpickle
- 17-06-19 - added fix for handling numpy based data <https://github.com/jsonpickle/jsonpickle/issues/147>
'''


import pickle
import codecs
import sys
import re
import os
from random import shuffle
import math
import shutil
import json
import pexpect
import time
import pdb
#import jsonpickle
#import jsonpickle.ext.numpy as jsonpickle_numpy
#jsonpickle_numpy.register_handlers()
from zlib import adler32
from inspect import getmembers, getargvalues, currentframe
import requests
from pexpect.replwrap import REPLWrapper


baseDir = '/NLPShare/Alcohol/'
dataDir = baseDir + 'data/'
adeBaseDir = '/NLPShare/ADE/'
adeDataDir = '/NLPShare/ADE/data/'

ancNoteTypes = dataDir + 'anc_note_types.txt'
labNoteTypes = dataDir + 'lab_note_types.txt'
otherNoteTypes = dataDir + 'other_note_types.txt'
allNotes = dataDir + 'all_notes.json'
allDiags = dataDir + 'all_diags.json'
allNotesWithDiags = dataDir + 'all_notes_with_diags.json'
adeIrbNotes = adeBaseDir + 'irb_209962_note_08082017.txt'
adeIrbPtList = adeBaseDir + 'irb_209962_pt_list_08082017.txt'
adePtListCsv = adeBaseDir + 'PatientList_209962.csv'
adeAllNotes = adeDataDir + 'all_notes.json'
logFile = dataDir + 'logs.txt'
ripTest = '''>>> fp = 6
>>> fn = 10
>>> tp = 18
>>> tn = 70
>>> pre, rec, f1 = calcScores(tp, fp, fn, tn)
>>> pre
0.75
>>> rec
>>> f1'''
ripTest2 = '''>>> audits = []
>>> with open(dataDir + 'audit_mrns.txt') as fo:
...  audits = fo.read().split('\\n')
... 
>>> len(audits)
1510
>>> audits[0]
'MRN'
>>> audits[-1]
''
>>> audits.pop()
''
>>> audits.pop(0)
'MRN'
>>> len(audits)
1508'''
calls = 0
mimic_bin = '/NLPShare/Lib/Word2Vec/Models/mimic.bin'
dist = '/NLPShare/Lib/Word2Vec/word2vec/distance'


class UMLSClient():

    def __init__(self, api_key, cache_path=''):
        self.api_key = api_key
        self.auth_uri="https://utslogin.nlm.nih.gov"
        self.auth_endpoint = "/cas/v1/api-key"
        self.service="http://umlsks.nlm.nih.gov"
        if not cache_path: cache_path = os.environ['HOME'] + '/umls_cache.json'
        self.cache_path = cache_path
        self.cache = {} if not os.path.exists(cache_path) else loadJson(cache_path)
        self.access_cnt = 0
        self.tgt = None
        self.st = None

    def save_cache(self):
        saveJson(self.cache, self.cache_path)
        return

    def gettgt(self):
        params = {'apikey': self.api_key}
        h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", "User-Agent":"python" }
        r = requests.post(self.auth_uri+self.auth_endpoint,data=params,headers=h)
        #response = fromstring(r.text)
        tgt = re_findall('action=.+cas', r.text, 0)[8:]
        if not tgt: raise Exception('UMLS authentication failed')
        self.tgt = tgt
        return tgt

    def getst(self, tgt=''):
        if not tgt: tgt = self.tgt or self.gettgt()
        params = {'service': self.service}
        h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", "User-Agent":"python" }
        r = requests.post(tgt, data=params,headers=h)
        st = r.text
        self.st = st
        return st

    def query_umls(self, identifier, tgt=None, source=None, version='current'):
        # get info from UMLS
        uri = "https://uts-ws.nlm.nih.gov"
        if not tgt: tgt = self.tgt or self.gettgt()
        content_endpoint = '/rest/content/%s/CUI/%s' % (version, identifier) if not source else '/rest/content/%s/source/%s/%s' % (str(version), str(source), identifier)
        query = {'ticket': self.getst(tgt)}
        r = requests.get(uri+content_endpoint,params=query)
        r.encoding = 'utf-8'
        items  = json.loads(r.text)
        jsonData = items["result"]
        if not 'cuis' in self.cache: self.cache['cuis'] = {}
        self.cache['cuis'][identifier] = jsonData
        self.access_cnt += 1
        if self.access_cnt >= 15: self.save_cache(); self.access_cnt = 0
        return jsonData

    def find_cui(self, identifier):
        # seek a cui in cache
        if not 'cuis' in self.cache or not identifier in self.cache['cuis']: return self.query_umls(identifier)
        return self.cache['cuis'][identifier]


class Distance():
    # Word2Vec distance wrapper by default

    def __init__(self, cmd='', prompt=None, rx=None):
        if not cmd: cmd = '{} {}'.format(dist, mimic_bin)
        if not prompt: prompt = 'Enter word or sentence (EXIT to break): '

        if isinstance(cmd, str):
            self._repl = REPLWrapper(cmd, prompt, None)

        else:
            self._repl = cmd
        self.nodes = []
        self.rx = rx if rx else '\s+(?P<Word>\S+)\t+.*'

    def find(self, words, num, max_levels=1, unique=True, level=0):
        first = self._repl.run_command(words, None).split('\n')[5:num+5]
        first = [re.match(self.rx, line).group('Word') for line in first]

        if level < max_levels:
            rest = [Distance(self._repl).find(first[idx], num, max_levels, level=level+1) for idx in range(len(first))]
            first.extend(rest)
            first = [word for sublist in first if isinstance(sublist, list) for word in sublist]
            if unique: first = list(set(first))
        return first


### For pickling operations

def loadPickle(fName):
    obj = None

    with open(fName, 'rb') as fo:
        obj = pickle.load(fo)
    return obj

def savePickle(obj, fName):

    with open(fName, 'wb') as fo:
        pickle.dump(obj, fo)
    return

### For command line operations

def readStdin():
    lines = []

    for line in sys.stdin.readlines():
        lines.append(line.strip())
    return lines

def writeStdout(lines, ofile=None):
    temp = None

    if not ofile == None:
        try:
            temp = sys.stdout
            sys.stdout = open(ofile, 'a')

        except Exception as e:
            print('Failed to use ' + ofile)

    for line in lines:
        sys.stdout.write(line)

    if not temp == None and not temp == sys.stdout:
        sys.stdout.close()
        sys.stdout = temp
    return

def writeStderr(lines):

    for line in lines:
        sys.stderr.write(line)
    return

def getCmdLine():
    return sys.argv

### For data search & manipulation

def pyCut(lines, delimiter=',', columns=['0'], errors='ignore'):
    '''
    Generator to cut lines based on column #s (1-based) and possibly rearrange order
    - Should work with strings and arrays
    - NB: may be broken by dynamically generated lists
    '''
    nline = None
    err = 0

    for line in lines:
        line = line.split(delimiter)

        try:

            for col in columns:

                if not ':' in col:
                    # simple base form
                    nline.append(line[int(col)])

                else:
                    splice = col.split(':')
                    nline.append(line[int(splice[0]) : int(splice[1])])
                    #raise Exception('Range splices not yet supported!')
            yield nline + '\n'  # should create a generator that returns individual lines
            
        except Exception as e:
            writeStderr(e.args)
            err += 1

def pyGrep(lines, pattern):
    pattern = re.compile(pattern)

    for line in lines:

        if not re.search(pattern, line) == None:
            yield line

def getFileList(path, recurse=False):
    
    for dirname, dirnames, filenames in os.walk(path):

        if not recurse:
            # TODO: move out of 'for'
            dirList = os.listdir(path)
            if not path[-1] == '/': path += '/'

            for fName in dirList:
                yield path + fName
            return
        # print path to all subdirectories first.
        #for subdirname in dirnames:
        #    print(os.path.join(dirname, subdirname))

        # print path to all filenames.
        for filename in filenames:
            print(os.path.join(dirname, filename))

def gridSearchAOR(p=None, construct='', results=[], doEval=False, funcList=[], resume=[]):
    # params is a list of dicts/lists of lists
    params = [{'methods': ['method1', 'method2']}, ['pos1arg1', 'pos1arg2'], ['pos2arg1', 'pos2arg2'],
              {'key1': ['a1-1', 'a1-2']}, {'key2': ['a2-1', 'a2-2']}] if p == None else p[:]

    if not params == []:
        # grab and process the first param
        param = params.pop(0)
        last_idx = 0

        if type(param) == type({}):
            # process dictionary
            kName = ''
            for key in param:
                kName = key

            for idx in range(len(param[kName])):
                result = None
                if idx < last_idx: idx = last_idx
                item = param[kName][idx]

                try:
                    if kName == 'methods':
                        # processing the methods
                        result = gridSearchAOR(params, item + '(', results, resume=resume)  # start constructing method call

                    else:
                        # processing named args

                        if type(item) == type('') and not item == 'False' and not item == 'True' and not item == 'None':
                            item = '\"%s\"' % item
                        result = gridSearchAOR(params, '%s %s=%s,' % (construct, kName, item), results, resume=resume)
                        #if result[-1] == ')' and not construct == '': return result

                    if construct == '' and not result == []:
                        # back on top
                        #results.append(result)
                        pass

                except KeyboardInterrupt:
                    raise

        elif type(param) == type([]):
            # process list, ie positional args

            for idx in range(len(param)):
                # processing positional args
                if idx < last_idx: idx = last_idx
                item = param[idx]

                try:
                    if type(item) == type('') and not item == 'False' and not item == 'True' and not item == 'None':
                        item = '\"%s\"' % item
                    result = gridSearchAOR(params, '%s %s,' % (construct, item), results, resume=resume)

                except KeyboardInterrupt:
                    raise

    else:
        # no more params to process
        result = construct[:-1] + ' )' # complete method call
        if not result in results: results.append(result)
        return result
    if not construct == '': return  # Only continue if we're at the top level
    if not doEval: return results

    for idx in range(len(results)):
        # evaluate them all
        print('Evaluating call #%d %s...' % (idx, results[idx]))

        try:
            results[idx] = [results[idx], eval(results[idx])]

        except Exception as e:
            print('Error in #%d, %s' % (idx, str(e.args)))
            results[idx] = [results[idx], str(e.args)]

    print('Grid search complete! Returning results.')
    return results

def getExpNum(tracker=''):
    # get and increment the experiement number on each call for autonaming
    tracking = loadJson(tracker) if os.path.exists(tracker) else {'exp_num': 0}
    expNum = tracking['exp_num']
    tracking['exp_num'] += 1
    saveJson(tracking, tracker)
    return expNum

def fileList(path, fullpath=False):
    nameList = os.listdir(path)

    if fullpath:

        for idx in range(len(nameList)):
            nameList[idx] = path + '/' + nameList[idx]
    return nameList

def splitDir(srcDir, destDir, percentOut, random=True, test=False):
    content = fileList(srcDir, True)
    numOut = len(content) - math.ceil(percentOut / 100 * len(content))  # take from end
    if not os.path.exists(srcDir): raise Exception('Source dir %s doesn\'t exist!' % srcDir)
    ensureDirs(destDir)

    if random:
        shuffle(content)

    if test:
        print('Old dir: %s\n\nnew dir: %s' % (content[:numOut], content[numOut:]))

    else:

        for path in content[numOut:]:
            shutil.move(path, destDir)
    print('Moved %d of %d files to %s' % (len(content) - numOut, len(content), destDir))
    #return content[:numOut], content[numOut:]

def calcScores(tp=0, fp=0, fn=0, tn=0):
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * ((precision * recall) / (precision + recall))
    return precision, recall, f1

def loadJson(fName):
    obj = None

    with open(fName) as fo:
        obj = json.load(fo)
        #obj = jsonpickle.decode(fo.read())
    return obj

def saveJson(obj, fName):

    with open(fName, 'w') as fo:
        json.dump(obj, fo)
        #fo.write(jsonpickle.encode(obj))
    return

def pesh(cmd, out=sys.stdout, shell='/bin/bash', debug=False):
    # takes command as a string or list
    result = ''
    if debug: print('DBG: cmd = \'%s\' & out = %s' % (cmd, str(out)))

    if out == False and type(out) == type(False):
        # run and forget; need multiprocess to prevent pexpect killing or blocking
        if debug: print('DBG: running in separate process')
        proc = Process(target=launch, args=([cmd, shell])).start()
        return 1
    child = pexpect.spawnu(shell, ['-c', cmd] if isinstance(cmd, str) else cmd)

    if not out == sys.stdout:
        result = out
        out = open(TMP_FILE, 'w')
    child.logfile = out
    child.expect([pexpect.EOF, pexpect.TIMEOUT])  # command complete and exited
    #sleep(5)

    if not result == False and child.isalive():
        # block until the child exits (normal behavior)
        # otherwise, don't wait for a return
        print('Waiting for child process...')
        child.wait()

    if out == sys.stdout:
        # output went to standard out or not waiting for child to end
        return 1
    out.close()
    lines = []

    with open(TMP_FILE) as fo:

        for line in fo:
            lines.append(line.strip())
    if debug: print('DBG: lines = %s' % str(lines))

    if type(result) == type(0):
        # get line specified by number, or last line
        if result < len(lines): return str(lines[result])

    if result == 'all':
        # all lines
        return lines

    if type(result) == type(''):
        # get line specified by pattern

        for line in lines:

            if result in line:  # TODO: make into regex match
                return line
        return None
    #raise Exception('Something went wrong in pesh')

def launch(cmd, shell='/bin/bash'):
    child = pexpect.spawnu(shell, ['-c', cmd] if type(cmd) == type('') else cmd, timeout=None)
    child.expect([pexpect.EOF, pexpect.TIMEOUT])

def currentTime():
    # 17-06-09
    return time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())

def writeLog(msg, print_=True, log=None):
    # 17-06-11
    global logFile
    if log: logFile = log

    with open(logFile, 'a') as lf:
        lf.write(msg + '\n')
    if print_: print(msg)
    return

def ensureDirs(*paths):
    # 17-06-11

    for path in paths:

        if isinstance(path, list):

            for sub in path:
                if not os.path.exists(sub): os.makedirs(sub)

        else:
            if not os.path.exists(path): os.makedirs(path)
    return

def loadText(fName):
    # 17-06-12

    with open(fName) as f:
        return f.read()

def saveText(text, fName):
    # 17-06-12

    with open(fName, 'w') as f:
        return f.write(text)

def runInterpDump(text):
    # 17-06-15
    # run commands directly copied from the Python interpreter
    multiline = False
    cache = []
    results = []
    #pdb.set_trace()

    for line in text.split('\n'):
        results.append(line)
        if re.match('^>>>\s+$', line): continue

        if line.startswith('>>> ') and line.endswith(':'):
            # start a block
            multiline = True
            cache = [line[4:]]
            continue

        if re.match('^\.{3,3}\s+$', line):
            # end a block
            multiline = False

            try:
                exec('\n'.join(cache), globals())

            except Exception as e:
                results.append(str(e))
            cache = []
            continue

        if line.startswith('... '):
            cache.append(line[4:])
            continue

        if line.startswith('>>> '):
            # regular 1 line commands
            line = line[4:]
            result = None

            try:
                # handle as expression
                result = str(eval(line, globals()))

            except SyntaxError:
                # handle as statement(s)
                exec(line, globals())
                result = None  # change to captured

            except Exception as e:
                # it's all broken
                result = str(e)
            results.append(result)
    return '\n'.join(r for r in results if isinstance(r, str))

def hash_sum(data):
    # 17-07-07
    return adler32(bytes(data, 'utf-8'))

def members(itm, print_=True):
    # 17-07-08
    mems = []
    for mem in getmembers(itm):
        if print_: print(mem)
        mems.append(mem)
    return mems

def slack_post(text='', channel='', botName='', botIcon=''):
    # 17-07-31
    text = 'Testing webhook' if text == '' else text
    botName = 'lnlp-bot' if botName == '' else botName
    channel = '#general' if channel == '' else channel
    botIcon = ':robot_face:' if botIcon == '' else botIcon
    payload = {'text': text, 'username': botName, 'channel': channel}

    if '://' in botIcon:
        payload['icon_url'] = botIcon

    else:
        payload['icon_emoji'] = botIcon
    payload = json.dumps(payload)
    print('Posting to Slack...')
    cmd = 'curl -X POST --data-urlencode \'payload=%s\' %s' % (payload, os.environ['LNLP_SLACK_HOOK'])
    pesh(cmd)
    return

def commit_me(tracker='', name='', path=''):
    # 17-08-01 Commit after each change
    if not name: name = sys.argv[0]
    if not name: return  # prob running pure interactive session
    if name.startswith('./'): name = name[2:]
    if not path: path = '%s/%s' % (os.getcwd(), name)
    last_dir = os.getcwd()
    os.chdir(os.path.dirname(path))
    p_hash = hash_sum(path)
    f_hash = hash_sum(loadText(path))
    t_name = 'commit_me_%s' % (p_hash)
    tracking = loadJson(tracker) if os.path.exists(tracker) else {t_name: f_hash}
    if t_name in tracking and tracking[t_name] == f_hash: return
    c_msg = '%s: auto-commit %s with hash %s' % (currentTime(), path, f_hash)
    pesh('git add %s' % (name))
    pesh('git commit -m "%s"' % (c_msg))
    os.chdir(last_dir)
    tracking[t_name] = f_hash
    saveJson(tracking, tracker)
    return f_hash

def get_path_from_func(func):
    # 17-08-01
    return func.__globals__['__file__']

def path_name_prefix(pref, path):
    # 17-08-01
    return '%s/%s%s' % (os.path.dirname(path), pref, path.split('/')[-1])

def cc_to_sc(name):
    # 17-08-12 - convert camelCase to snake_case
    s = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s).lower()

def str_to_dict(s, main_sep, map_sep, use_re=False):
    # 17-08-01 - initial
    # -12 - update to support regex
    # -09-11 - default if no value for a key
    final = {}
    items = s.split(main_sep) if not use_re else re.split(main_sep, s)

    for item in items:
        item = item.split(map_sep) if not use_re else re.split(map_sep, item)
        final[item[0]] = item[1] if len(item) == 2 else None
    return final

def re_findall(pat, s_, idx=None):
    # 17-08-15 - re.findall replacement that does what's expected
    res = []
    pos = 0

    while True:
        match = re.search(pat, s_)
        if not match: break
        rnge = match.span()
        res.append(s_[rnge[0]:rnge[1]])
        pos = rnge[1]
        s_ = s_[pos:]
    if len(res) >= 1 and isinstance(idx, int): return res[idx]
    return res

def re_index(match, s_):
    # 17-08-17 -

    if isinstance(s_, dict):
        for pat in s_:
            if not re.match(pat, match): continue
            return s_[pat]

    if isinstance(s_, list):
        for idx in range(len(s_)):
            if not re.match(s_[idx], match): continue
            return s_[idx]
    return None

if __name__ == '__main__':
    print('This is a library module not meant to be run directly!')
commit_me(dataDir + 'tracking.json', 'common.py')
