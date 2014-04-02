'''This is a module that tries to use emcee to solve SNooPy models.
The SN object should have all the necessary ingredients. All that is
left is to define prior probabilities.'''

import emcee
import numpy as np
from scipy.optimize import minimize
import types

gconst = -0.5*np.log(2*np.pi)

def builtin_priors(x, st):
   '''Some built-in priors that are simple strings that we parse.'''
   if st[0] not in ['U','G','E']:
      raise ValueError, "I don't understand the prior code %s" % st
   if st[0] == 'U':
      '''uniform prior:  U,l,u'''
      u,l = map(float, st.split(',')[1:])
      if not u < x < l:
         return -np.inf
      return 0
   elif st[0] == 'G':
      '''Gaussian prior, G(mu,sigma) = 1/sigma/sqrt(2*pi)*exp((x-mu)^2/2/sigma^2)'''
      mu,sigma = map(float, st.split(',')[1:])
      return gconst - 0.5*np.power(x - mu,2)/sigma**2 - np.log(sigma)
   elif st[0] == 'E':
      '''exponential prior, E(x,tau) = 1/tau*exp(-x/tau).'''
      tau = float(st.split(',')[1])
      return -np.log(tau) - x/tau

def guess(varinfo, snobj):
   '''Get starting values from the fitter.'''
   p = np.zeros((varinfo['Nvar'],))
   for id,var in enumerate(varinfo['free']):
      if snobj.model.parameters[var] is None:
         raise ValueError, "model parameters not set, run initial fit() first"
      p[id] = snobj.model.parameters[var]
   return p



def setup_varinfo(snobj, args):
   '''Given a sn object and its associated model, setup the varinfo.'''
   varinfo = {}
   varinfo['varlist'] = snobj.model.parameters.keys()
   i  = 0
   varinfo['free'] = []
   for var in varinfo['varlist']:
      varinfo[var] = {}
      if var in args:
         if type(args[var]) is types.FloatType:
            varinfo[var]['value'] = args[var]
            varinfo[var]['fixed'] = True
         elif type(args[var]) is types.FunctionType:
            varinfo[var]['fixed'] = False
            varinfo[var]['index'] = i
            varinfo['free'].append(var)
            i += 1
            varinfo[var]['prior'] = args[var]
            varinfo[var]['prior_type'] = 'function'
         elif type(args[var]) is types.StringType:
            varinfo[var]['fixed'] = False
            varinfo[var]['index'] = i
            varinfo['free'].append(var)
            i += 1
            varinfo[var]['prior'] = args[var]
            varinfo[var]['prior_type'] = 'builtin'
      else:
         varinfo[var]['fixed'] = False
         varinfo[var]['index'] = i
         varinfo['free'].append(var)
         i += 1
         varinfo[var]['prior_type'] = 'model'
   varinfo['Nvar'] = i
   return varinfo


def lnprior(p, varinfo, snobj):
   lp = 0
   for id,var in enumerate(varinfo['free']):
      val = p[id]
      if varinfo[var]['prior_type'] == 'function':
         lp += varinfo[var]['prior'](val)
      elif varinfo[var]['prior_type'] == 'builtin':
         lp += builtin_priors(val, varinfo[var]['prior'])
      elif varinfo[var]['prior_type'] == 'model':
         lp += snobj.model.prior(var,val)
   return lp

def lnlike(p, varinfo, snobj, bands):
   # first, assign all variables to the model:
   for id,var in enumerate(varinfo['varlist']):
      if varinfo[var]['fixed']:
         snobj.model.parameters[var] = varinfo[var]['value']
      else:
         val = p[varinfo[var]['index']]
         snobj.model.parameters[var] = val

   lp = 0
   for band in bands:
      mod,err,mask = snobj.model.__call__(band, snobj.data[band].MJD)
      if snobj.model.model_in_mags:
         f = np.power(10, -0.4*(mod - snobj.data[band].filter.zp))
         cov_f = np.power(f*err/1.0857,2)
      else:
         f = mod
         cov_f = np.power(err, 2)
      m = mask*snobj.data[band].mask
      if not np.sometrue(m):
         # We're outside the support of the data
         return -np.inf
      denom = cov_f + np.power(snobj.data[band].e_flux,2)
      lp = lp - 0.5*np.sum(np.power(snobj.data[band].flux - f,2)/denom + \
            np.log(denom) + np.log(2*np.pi))
   return lp

def lnprob(p, varinfo, snobj, bands):

   lprior = lnprior(p, varinfo, snobj)
   if not np.isfinite(lprior):
      return -np.inf
   return lprior + lnlike(p, varinfo, snobj, bands)


def generateSampler(snobj, bands, nwalkers, threads=1, **args):
   '''Generate an emcee sampler from the sn object [snobj] and its
   associated model (chosen with snobj.choose_model). You must set the
   number of walkers (see emcee documentation).  You can control
   the priors of the model by passing them as arguments. For example,
   using Tmax='G,1000,10' would use a Gaussian prior with mean 1000
   and standard deviation 10. You can also set any parameter to a
   constant value. Lastly, you can set a parameter equal to a function
   that takes a single argument and returns the log-probability as
   a prior. This function returns:  sampler,p0
   where sampler is an emcee sampler, and p0 is [nwalkers] starting
   points.'''
   if not snobj.model._fbands:
      raise ValueError, "You need to do an initial fit to the SN first"
   vinfo = setup_varinfo(snobj, args)
   p = guess(vinfo, snobj)
   ndim = p.shape[0]
   p0 = [p + 1.0e-4*np.random.randn(ndim) for i in range(nwalkers)]
   sampler = emcee.EnsembleSampler(nwalkers, ndim, lnprob, args=(vinfo, snobj, bands),
         threads=threads)
   return sampler,vinfo,p0






