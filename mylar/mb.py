#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import re
import time
import threading
import urllib, urllib2
from xml.dom.minidom import parseString, Element

import mylar
from mylar import logger, db, cv
from mylar.helpers import multikeysort, replace_all, cleanName, cvapi_check, listLibrary

mb_lock = threading.Lock()


def pullsearch(comicapi,comicquery,offset,explicit,type):
    u_comicquery = urllib.quote(comicquery.encode('utf-8').strip())
    u_comicquery = u_comicquery.replace(" ", "%20")

    if explicit == 'all' or explicit == 'loose':
        PULLURL = mylar.CVURL + 'search?api_key=' + str(comicapi) + '&resources=' + str(type) + '&query=' + u_comicquery + '&field_list=id,name,start_year,site_detail_url,count_of_issues,image,publisher,description&format=xml&page=' + str(offset)

    else:
        # 02/22/2014 use the volume filter label to get the right results.
        # add the 's' to the end of type to pluralize the caption (it's needed)
        if type == 'story_arc':
            u_comicquery = re.sub("%20AND%20", "%20", u_comicquery)
        PULLURL = mylar.CVURL + str(type) + 's?api_key=' + str(comicapi) + '&filter=name:' + u_comicquery + '&field_list=id,name,start_year,site_detail_url,count_of_issues,image,publisher,description&format=xml&offset=' + str(offset) # 2012/22/02 - CVAPI flipped back to offset instead of page
    #logger.info('PULLURL: ' + str(PULLURL))
    #all these imports are standard on most modern python implementations
    #CV API Check here.
    if mylar.CVAPI_COUNT == 0 or mylar.CVAPI_COUNT >= mylar.CVAPI_MAX:
        cvapi_check()
    #download the file:
    try:
        file = urllib2.urlopen(PULLURL)
    except urllib2.HTTPError, err:
        logger.error('err : ' + str(err))
        logger.error("There was a major problem retrieving data from ComicVine - on their end. You'll have to try again later most likely.")
        return        
    #increment CV API counter.
    mylar.CVAPI_COUNT +=1
    #convert to string:
    data = file.read()
    #close file because we dont need it anymore:
    file.close()
    #parse the xml you downloaded
    dom = parseString(data)
    return dom

def findComic(name, mode, issue, limityear=None, explicit=None, type=None):

    #with mb_lock:       
    comiclist = []
    comicResults = None
    comicLibrary = listLibrary()
    
    chars = set('!?*')
    if any((c in chars) for c in name):
        name = '"'+name+'"'

    #print ("limityear: " + str(limityear))            
    if limityear is None: limityear = 'None'
    
    comicquery = name
    #comicquery=name.replace(" ", "%20")

    if explicit is None:
        #logger.fdebug('explicit is None. Setting to Default mode of ALL search words.')
        #comicquery=name.replace(" ", " AND ")
        explicit = 'all'

    #OR
    if explicit == 'loose':
        logger.fdebug('Changing to loose mode - this will match ANY of the search words')
        comicquery = name.replace(" ", " OR ")
    elif explicit == 'explicit':
        logger.fdebug('Changing to explicit mode - this will match explicitly on the EXACT words')
        comicquery=name.replace(" ", " AND ")
    else:
        logger.fdebug('Default search mode - this will match on ALL search words')
        comicquery = name.replace(" ", " AND ")
        explicit = 'all'


    if mylar.COMICVINE_API == 'None' or mylar.COMICVINE_API is None or mylar.COMICVINE_API == mylar.DEFAULT_CVAPI:
        logger.warn('You have not specified your own ComicVine API key - alot of things will be limited. Get your own @ http://api.comicvine.com.')
        comicapi = mylar.DEFAULT_CVAPI
    else:
        comicapi = mylar.COMICVINE_API

    if type is None:
        type = 'volume'

    #let's find out how many results we get from the query...    
    searched = pullsearch(comicapi,comicquery,0,explicit,type)
    if searched is None: return False
    totalResults = searched.getElementsByTagName('number_of_total_results')[0].firstChild.wholeText
    logger.fdebug("there are " + str(totalResults) + " search results...")
    if not totalResults:
        return False
    countResults = 0
    while (countResults < int(totalResults)):
        #logger.fdebug("querying " + str(countResults))
        if countResults > 0:
            #2012/22/02 - CV API flipped back to offset usage instead of page 
            if explicit == 'all' or explicit == 'loose':
                #all / loose uses page for offset
                offsetcount = (countResults/100) + 1
            else:
                #explicit uses offset
                offsetcount = countResults
            
            searched = pullsearch(comicapi,comicquery,offsetcount,explicit,type)
        comicResults = searched.getElementsByTagName(type) #('volume')
        body = ''
        n = 0        
        if not comicResults:
           break        
        for result in comicResults:
                #retrieve the first xml tag (<tag>data</tag>)
                #that the parser finds with name tagName:
                if type == 'story_arc':
                    #call cv.py here to find out issue count in story arc
                    try:
                        logger.fdebug('story_arc ascension')
                        names = len( result.getElementsByTagName('name') )
                        n = 0
                        logger.fdebug('length: ' + str(names))
                        while ( n < names ):
                            logger.fdebug(result.getElementsByTagName('name')[n].parentNode.nodeName)
                            if result.getElementsByTagName('name')[n].parentNode.nodeName == 'story_arc':
                                logger.fdebug('yes')
                                try:
                                    xmlTag = result.getElementsByTagName('name')[n].firstChild.wholeText
                                    xmlTag = xmlTag.rstrip()
                                    logger.fdebug('name: ' + str(xmlTag))
                                except:
                                    logger.error('There was a problem retrieving the given data from ComicVine. Ensure that www.comicvine.com is accessible.')
                                    return

                            elif result.getElementsByTagName('name')[n].parentNode.nodeName == 'publisher':
                                logger.fdebug('publisher check.')
                                xmlpub = result.getElementsByTagName('name')[n].firstChild.wholeText

                            n+=1
                    except:
                        logger.warn('error retrieving story arc search results.')
                        return

                    siteurl = len( result.getElementsByTagName('site_detail_url') )
                    s = 0
                    logger.fdebug('length: ' + str(names))
                    xmlurl = None
                    while ( s < siteurl ):
                        logger.fdebug(result.getElementsByTagName('site_detail_url')[s].parentNode.nodeName)
                        if result.getElementsByTagName('site_detail_url')[s].parentNode.nodeName == 'story_arc':
                            try:
                                xmlurl = result.getElementsByTagName('site_detail_url')[s].firstChild.wholeText
                            except:
                                logger.error('There was a problem retrieving the given data from ComicVine. Ensure that www.comicvine.com is accessible.')
                                return
                        s+=1

                    xmlid = result.getElementsByTagName('id')[0].firstChild.wholeText

                    if xmlid is not None:
                        #respawn to the exact id for the story arc and count the # of issues present.
                        ARCPULL_URL = mylar.CVURL + 'story_arc/4045-' + str(xmlid) + '/?api_key=' + str(comicapi) + '&field_list=issues,name,first_appeared_in_issue&format=xml&offset=0'
                        logger.fdebug('arcpull_url:' + str(ARCPULL_URL))
                        if mylar.CVAPI_COUNT == 0 or mylar.CVAPI_COUNT >= mylar.CVAPI_MAX:
                            cvapi_check()
                        try:
                            file = urllib2.urlopen(ARCPULL_URL)
                        except urllib2.HTTPError, err:
                            logger.error('err : ' + str(err))
                            logger.error('There was a major problem retrieving data from ComicVine - on their end.')
                            return

                        mylar.CVAPI_COUNT +=1
                        arcdata = file.read()
                        file.close()
                        arcdom = parseString(arcdata)

                        try:
                            logger.fdebug('story_arc ascension')
                            issuecount = len( arcdom.getElementsByTagName('issue') )
                        except:
                            logger.fdebug('unable to retrive issue count - nullifying value.')
                            issuecount = 0

                        try:
                            firstid = None
                            arcyear = None
                            fid = len ( arcdom.getElementsByTagName('id') )
                            fi = 0
                            while (fi < fid):
                                if arcdom.getElementsByTagName('id')[fi].parentNode.nodeName == 'first_appeared_in_issue':
                                    if not arcdom.getElementsByTagName('id')[fi].firstChild.wholeText == xmlid:
                                        logger.fdebug('hit it.')
                                        firstid = arcdom.getElementsByTagName('id')[fi].firstChild.wholeText
                                        break
                            fi+=1
                            logger.fdebug('firstid: ' + str(firstid))
                            if firstID is not None:
                                firstdom = cv.pulldetails(comicid=None, type='firstissue', issueid=firstid)
                                logger.fdebug('success')
                                arcyear = cv.GetFirstIssue(firstid,firstdom)
                        except:
                            logger.fdebug('Unable to retrieve first issue details. Not caclulating at this time.')

                    if (result.getElementsByTagName('image')[0].childNodes[0].nodeValue) is None:
                        xmlimage = result.getElementsByTagName('super_url')[0].firstChild.wholeText
                    else:
                        xmlimage = "cache/blankcover.jpg"

                    try:
                        xmldesc = result.getElementsByTagName('deck')[0].firstChild.wholeText
                    except:
                        xmldesc = "None"
                            
                        if xmlid in comicLibrary:
                            haveit = "Yes"
                        else:
						haveit = "No"

                    comiclist.append({
                            'name':                 xmlTag,
                            'comicyear':            arcyear,
                            'comicid':              xmlid,
                            'url':                  xmlurl,
                            'issues':               issuecount,
                            'comicimage':           xmlimage,
                            'publisher':            xmlpub,
                            'description':          xmldesc, 
                            'haveit':   haveit
                            })

    
                else:
                    xmlcnt = result.getElementsByTagName('count_of_issues')[0].firstChild.wholeText
                    #here we can determine what called us, and either start gathering all issues or just limited ones.
                    #print ("n: " + str(n) + "--xmcnt" + str(xmlcnt))
                    if issue is not None and str(issue).isdigit():
                        #this gets buggered up with NEW/ONGOING series because the db hasn't been updated
                        #to reflect the proper count. Drop it by 1 to make sure.
                        limiter = int(issue) - 1
                    else: limiter = 0
                    if int(xmlcnt) >= limiter:
                    
                        xmlTag = result.getElementsByTagName('name')[0].firstChild.wholeText
                        if (result.getElementsByTagName('start_year')[0].firstChild) is not None:
                            xmlYr = result.getElementsByTagName('start_year')[0].firstChild.wholeText
                        else: xmlYr = "0000"
                        if xmlYr in limityear or limityear == 'None':
                            xmlurl = result.getElementsByTagName('site_detail_url')[0].firstChild.wholeText
                            xmlid = result.getElementsByTagName('id')[0].firstChild.wholeText
                            publishers = result.getElementsByTagName('publisher')
                            if len(publishers) > 0:
                                pubnames = publishers[0].getElementsByTagName('name')
                                if len(pubnames) >0:
                                    xmlpub = pubnames[0].firstChild.wholeText
                                else:
                                    xmlpub = "Unknown"
                            else:
                                xmlpub = "Unknown"
                            if (result.getElementsByTagName('name')[0].childNodes[0].nodeValue) is None:
                                xmlimage = result.getElementsByTagName('super_url')[0].firstChild.wholeText
                            else:
                                xmlimage = "cache/blankcover.jpg"            

                            try:
                                xmldesc = result.getElementsByTagName('description')[0].firstChild.wholeText
                            except:
                                xmldesc = "None"
                            if xmlid in comicLibrary:
                                haveit = "Yes"
                            else:
                                haveit = "No"
                            comiclist.append({
                                    'name':             xmlTag,
                                    'comicyear':             xmlYr,
                                    'comicid':                xmlid,
                                    'url':                 xmlurl,
                                    'issues':            xmlcnt,
                                    'comicimage':          xmlimage,
                                    'publisher':            xmlpub,
                                    'description':          xmldesc,
                                    'haveit':   haveit
                                    })
                        else:
                            logger.fdebug('year: ' + str(xmlYr) + ' -  contraint not met. Has to be within ' + str(limityear)) 
                n+=1    
        #search results are limited to 100 and by pagination now...let's account for this.
        countResults = countResults + 100
   
    return comiclist, explicit
