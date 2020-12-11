#!/usr/bin/env python

# S. Rest

import numpy as np
import math
import sys,socket,os,re,io
from astropy.io import ascii
from astropy import units as u
from astropy.coordinates import Angle
from astropy.coordinates import SkyCoord
from astropy.table import Table
import argparse
from tools import rmfile
from tools import RaInDeg
from tools import DecInDeg
import pandas as pd
from astrotable import astrotableclass
from download_atlas_lc import download_atlas_lc_class
from SNloop import SNloopclass
from cleanup_lc import cleanuplcclass
from plot_lc import plotlcclass, dataPlot
from average_lc import averagelcclass
from offsetstats import offsetstatsclass
import sigmacut
from pdastro import pdastroclass, AandB

class downloadlcloopclass(cleanuplcclass,plotlcclass,averagelcclass,offsetstatsclass):
	def __init__(self):
		cleanuplcclass.__init__(self)
		plotlcclass.__init__(self)
		averagelcclass.__init__(self)
		self.download_atlas_lc = download_atlas_lc_class()

	def downloadlc(self, SNindex, lookbacktime_days=None, savelc=False, overwrite=False, fileformat=None, offsetindex=None):
		RA = self.RADECtable.t.at[offsetindex,'Ra']
		Dec = self.RADECtable.t.at[offsetindex,'Dec']

		self.download_atlas_lc.verbose = self.verbose
		self.download_atlas_lc.debug = self.debug
		self.download_atlas_lc.get_lc(RA,Dec,lookbacktime_days=lookbacktime_days)

		# read the lc into a pandas table
		self.lc.t = pd.read_csv(io.StringIO('\n'.join(self.download_atlas_lc.lcraw)),delim_whitespace=True,skipinitialspace=True)
		mask = np.zeros((len(self.lc.t)), dtype=int)
		self.lc.t = self.lc.t.assign(Mask=mask)
		
		# sort data by mjd
		self.lc.t = self.lc.t.sort_values(by=['MJD'],ignore_index=True)
		
		# delete any rows with duJy=0
		for index in range(len(self.lc.t['MJD'])):
			if self.lc.t.at[index,'duJy'] == 0:
				self.lc.t.drop(index)

		indices = self.lc.ix_remove_null(colnames='uJy')

		# save the lc file with the output filename
		if savelc:
			self.save_lc(SNindex=SNindex,indices=indices,overwrite=overwrite,fileformat=fileformat,offsetindex=offsetindex)
			for filt in ['c','o']:
				filename = self.lcbasename(SNindex=SNindex,filt=filt, offsetindex=offsetindex)+'.txt'
				if fileformat is None: 
					fileformat = self.cfg.params['output']['fileformat']
				detections4filt=np.where(self.lc.t['F']==filt)
				newindices = AandB(indices,detections4filt)

				if len(detections4filt[0]) is 0:
					print('Saving blank light curve: %s' % filename)
					self.lc.write(filename,index=False,indices=newindices,overwrite=True,verbose=False,columns=['MJD','m','dm',self.flux_colname,self.dflux_colname,'F','err','chi/N','RA','Dec','x','y','maj','min','phi','apfit','Sky','ZP','Obs','Mask'])
				else: 
					print('Saving light curve: %s' % filename)
					self.lc.write(filename, index=False, indices=newindices, overwrite=True, verbose=False)

	def defineRADEClist(self,RA,Dec,SNindex,pattern=None):
		self.RADECtable.t = pd.DataFrame(columns=self.RADECtable.t.columns)
		if not(pattern is None):
			pattern_list = pattern
			print('Pattern(s) set to ',pattern_list)
			OffsetID = 1
			foundflag = False

			RA = Angle(RaInDeg(self.t.at[SNindex,'ra']),u.degree) # why not just put in RA var?? lol
			Dec = Angle(DecInDeg(self.t.at[SNindex,'dec']),u.degree)
			#print('RA,Dec: %s %s %f %f' % (self.t.at[SNindex,'ra'],self.t.at[SNindex,'dec'],RA.degree,Dec.degree)) # delete me

			for pattern in pattern_list: 
				# number of offsets and radii depends on pattern specified in precursor.cfg or in args
				if pattern=='circle':
					PatternID = 1
					n = self.cfg.params['forcedphotpatterns']['circle']['n']
					radii = self.cfg.params['forcedphotpatterns']['circle']['radii']
				elif pattern=='box':
					PatternID = 2
					n = 4
					radii = [self.cfg.params['forcedphotpatterns']['box']['sidelength']]
				elif pattern=='closebright':
					PatternID = 3
					mindist = self.cfg.params['forcedphotpatterns']['closebright']['mindist']
					n = self.cfg.params['forcedphotpatterns']['closebright']['n']

					# query panstarrs for closest bright object and add to snlist.txt
					if self.cfg.params['forcedphotpatterns']['closebright']['autosearch'] is True:
						results = self.autosearch(RA.degree, Dec.degree, 20)
						print('Close bright objects found: \n',results)
						sys.exit(0)
						cbRA = '_' # FIX
						cbDec = '_' # FIX
						self.t.at[SNindex,'closebrightRA'] = Angle(RaInDeg(cbRA),u.degree)
						self.t.at[SNindex,'closebrightDec'] = Angle(RaInDeg(cbDec),u.degree)
					# use coordinates listed in snlist.txt
					else:
						cbRA = Angle(RaInDeg(self.t.at[SNindex,'closebrightRA']),u.degree)
						cbDec = Angle(DecInDeg(self.t.at[SNindex,'closebrightDec']),u.degree)

					# radius is distance between SN and bright object
					c1 = SkyCoord(RA, Dec, frame='fk5')
					c2 = SkyCoord(cbRA, cbDec, frame='fk5')
					sep = c1.separation(c2)
					r1 = sep.arcsecond
					radii = [r1]

					if self.verbose:
						print('Minimum distance from SN to offset: ',mindist)
				else:
					raise RuntimeError("Pattern %s is not defined" % pattern)

				# sets up RADECtable, fills in OffsetID, Ra, Dec, RaNew, DecNew for (n*len(radii)) offsets
				if foundflag is False:
					foundflag = True
					df = pd.DataFrame([[0,0,RA.degree,Dec.degree,0,0,0,0,0,0]], columns=['OffsetID','PatternID','Ra','Dec','RaOffset','DecOffset','Radius','Ndet','Ndet_c','Ndet_o'])
					self.RADECtable.t = self.RADECtable.t.append(df, ignore_index=True)
				for radius in radii:
					R = Angle(radius,u.arcsec)

					# define center coordinates
					if pattern=='closebright':
						RAcenter = Angle(cbRA.degree,u.degree)
						Deccenter = Angle(cbDec.degree,u.degree)
					elif (pattern=='circle') or (pattern=='box'):	
						RAcenter = Angle(RA.degree,u.degree)
						Deccenter = Angle(Dec.degree,u.degree)
					else:
						raise RuntimeError('Pattern must be circle, box, or closebright!')

					#print('CENTER: ',RAcenter.degree,Deccenter.degree) # delete me
					#print('R = %f arcsec or %f deg or %f rad' % (R.arcsec,R.degree,R.radian)) # delete me

					for i in range(n):
						angle = Angle(i*360.0/n, u.degree)
						RAdistance = Angle(R.degree*math.cos(angle.radian),u.degree)
						RAoffset = Angle(RAdistance.degree*(1.0/math.cos(Deccenter.radian)),u.degree)
						RAnew = Angle(RAcenter.degree+RAoffset.degree,u.degree)
						DECoffset = Angle(R.degree*math.sin(angle.radian),u.degree)
						DECnew = Angle(Deccenter.degree+DECoffset.degree,u.degree)

						# check to see if offset location is within mindist arcsec from SN
						if pattern=='closebright':
							c1 = SkyCoord(RA, Dec, frame='fk5')
							#print(RAnew,DECnew) # delete me
							c2 = SkyCoord(RAnew, DECnew, frame='fk5')
							offset_sep = c1.separation(c2)
							offset_sep = offset_sep.arcsecond
							if offset_sep < mindist:
								print('Offset with OffsetID %d too close to SN with distance of %f arcsec, skipping...' % (OffsetID, offset_sep))
								continue
						df = pd.DataFrame([[OffsetID,PatternID,RAnew.degree,DECnew.degree,RAdistance.arcsec,DECoffset.arcsec,radius,0,0,0]],columns=['OffsetID','PatternID','Ra','Dec','RaOffset','DecOffset','Radius','Ndet','Ndet_c','Ndet_o'])
						self.RADECtable.t = self.RADECtable.t.append(df,ignore_index=True)

						if self.verbose>1:
							print('#\nAngle: %f deg' % angle.degree)
							print('#RA center: %f deg' % RAcenter.degree)
							print('#Dec center: %f deg' % Deccenter.degree)
							print('#RA distance: %f arcsec' % RAdistance.arcsec)
							print('#RA offset to be added to RA: %f arcsec' % RAoffset.arcsec)
							print('#Dec offset: %f arcsec' % DECoffset.arcsec)
						if self.verbose:
							print('#Angle: %.1f, new RA and Dec: %f, %f' % (angle.degree, RAnew.degree, DECnew.degree))
						OffsetID += 1
		else:
			RA = Angle(RaInDeg(self.t.at[SNindex,'ra']),u.degree) # just put in RA var
			Dec = Angle(DecInDeg(self.t.at[SNindex,'dec']),u.degree) # just put in Dec var
			df = pd.DataFrame([[0,0,RA.degree,Dec.degree,0,0,0,0,0,0]], columns=['OffsetID','PatternID','Ra','Dec','RaOffset','DecOffset','Radius','Ndet','Ndet_c','Ndet_o'])
			self.RADECtable.t = self.RADECtable.t.append(df, ignore_index=True)

	def downloadoffsetlc(self, SNindex, forcedphot_offset=False, lookbacktime_days=None, savelc=False, overwrite=False, fileformat=None,pattern=None):
		print('Offset status: ',forcedphot_offset)
		if forcedphot_offset == 'True':
			RA = self.t.at[SNindex,'ra']
			Dec = self.t.at[SNindex,'dec']
			
			self.defineRADEClist(RA,Dec,SNindex,pattern=pattern)
			print(self.RADECtable.write(index=True,overwrite=False))
			
			# add new row for each offset using data from RADECtable
			for i in range(len(self.RADECtable.t)):
				if self.verbose:
					print(self.RADECtable.write(indices=i, columns=['OffsetID','Ra','Dec']))

				#RA = self.RADECtable.t.at[i,'Ra']
				#Dec = self.RADECtable.t.at[i,'Dec']
				self.downloadlc(SNindex,
							 lookbacktime_days=lookbacktime_days,
							 savelc=savelc,
							 overwrite=overwrite,
							 fileformat=fileformat,
							 offsetindex=i)
				print('Length of lc: ',len(self.lc.t))
				self.RADECtable.t.loc[i,'Ndet']=len(self.lc.t)
				ofilt = np.where(self.lc.t['F']=='o')
				self.RADECtable.t.loc[i,'Ndet_o']=len(ofilt[0])
				cfilt = np.where(self.lc.t['F']=='c')
				self.RADECtable.t.loc[i,'Ndet_c']=len(cfilt[0])
			
			if savelc:
				self.saveRADEClist(SNindex,filt='c')
				self.saveRADEClist(SNindex,filt='o')
		else:
			print('Skipping forcedphot offsets lc for %s...' % self.t.at[SNindex,'tnsname'])
			# only add SN data in new row without offsets
			RA = self.t.at[SNindex,'ra']
			Dec = self.t.at[SNindex,'dec']

			self.defineRADEClist(RA,Dec,SNindex,pattern=None)
			if self.verbose>1:
				print(self.RADECtable.write(index=True,overwrite=False))

			
			for i in range(len(self.RADECtable.t)):
				if self.verbose:
					print(self.RADECtable.write(indices=i, columns=['OffsetID', 'Ra', 'Dec']))
				self.downloadlc(SNindex,
							 lookbacktime_days=lookbacktime_days,
							 savelc=savelc,
							 overwrite=overwrite,
							 fileformat=fileformat,
							 offsetindex=i)
				
				print('Length of lc: ',len(self.lc.t))
				self.RADECtable.t.loc[i,'Ndet']=len(self.lc.t)
				ofilt = np.where(self.lc.t['F']=='o')
				self.RADECtable.t.loc[i,'Ndet_o']=len(ofilt[0])
				cfilt = np.where(self.lc.t['F']=='c')
				self.RADECtable.t.loc[i,'Ndet_c']=len(cfilt[0])

			if savelc:
				#self.saveRADEClist(SNindex)
				self.saveRADEClist(SNindex,filt='c')
				self.saveRADEClist(SNindex,filt='o')

if __name__ == '__main__':

	downloadlc = downloadlcloopclass()
	parser = downloadlc.download_atlas_lc.define_optional_args()
	parser = downloadlc.define_options(parser=parser)
	args = parser.parse_args()

	SNindexlist = downloadlc.initialize(args)

	username = downloadlc.cfg.params['username']
	if username is False:
		username = os.environ['USER']
	if not(args.user is None):
		username = args.user
	print('ATLAS username: ', username)
	password=args.passwd
	print('ATLAS password length: ',len(password))

	downloadlc.download_atlas_lc.connect(args.atlasmachine,username,password)

	if not(args.pattern is None):
		pattern = args.pattern
	else:
		pattern = downloadlc.cfg.params['forcedphotpatterns']['patterns_to_use']

	for SNindex in SNindexlist:
		downloadlc.downloadoffsetlc(SNindex,
									lookbacktime_days=args.lookbacktime_days,
									savelc=args.savelc,
									overwrite=args.overwrite,
									fileformat=args.fileformat,
									pattern=pattern,
									forcedphot_offset=args.forcedphot_offset)
		for offsetindex in range(len(downloadlc.RADECtable.t)):
			downloadlc.cleanuplcloop(args,SNindex,offsetindex=offsetindex,filt=downloadlc.filt)
			if args.averagelc: 
				downloadlc.averagelcloop(args,SNindex,offsetindex=offsetindex)
		if args.forcedphot_offset:
			downloadlc.loadRADEClist(SNindex, filt=downloadlc.filt)
			downloadlc.offsetstatsloop(SNindex,filt=downloadlc.filt)
		if args.plot: 
			downloadlc.plotlcloop(args,SNindex)
