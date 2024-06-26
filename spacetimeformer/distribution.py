import math
from numbers import Number, Real

import torch
from torch.distributions import constraints
from torch.distributions.distribution import Distribution
from torch.distributions.utils import broadcast_all
import numpy as np

# Numerically stable and accurate implementation of the natural logarithm
# of the cumulative distribution function (CDF) for the standard
# Normal/Gaussian distribution in PyTorch. https://gist.github.com/chausies/011df759f167b17b5278264454fff379


def norm_cdf(x):
    return (1 + torch.erf(x/math.sqrt(2)))/2

def log_norm_cdf_helper(x):
    a = 0.344
    b = 5.334
    return ((1 - a)*x + a*x**2+b).sqrt()

def log_norm_cdf(x):
    thresh = 3
    out = x*0
    l = x<-thresh
    g = x>thresh
    m = torch.logical_and(x>=-thresh, x<=thresh)
    out[m] = norm_cdf(x[m]).log()
    out[l] = -(
        (x[l]**2 + np.log(2*np.pi))/2 + 
        log_norm_cdf_helper(-x[l]).log()
        )
    out[g] = torch.log1p(-
        (-x[g]**2/2).exp()/np.sqrt(2*np.pi)/log_norm_cdf_helper(x[g])
        )
    return out

class SkewNormal(Distribution):
    r"""
    Creates a skew normal distribution parameterized by
    :attr:`loc`, :attr:`scale`, and :attr:`alpha`.

    Example::

        >>> # xdoctest: +IGNORE_WANT("non-deterministic")
        >>> m = SkewNormal(torch.tensor([0.0]), torch.tensor([1.0]), torch.tensor([0.0]))
        >>> m.sample()  # skew normal distribution with loc=0, scale=1, and alpha=0
        tensor([ 0.1046])

    Args:
        loc (float or Tensor): mean of the distribution (often referred to as mu)
        scale (float or Tensor): standard deviation of the distribution
            (often referred to as sigma)
        alpha (float or Tensor): skewness parameter of the distribution
    """
    arg_constraints = {"loc": constraints.real, "scale": constraints.positive, "alpha": constraints.real}
    support = constraints.real
    has_rsample = True

    @property
    def mean(self):
        delta = self.alpha / torch.sqrt(1 + self.alpha.pow(2))
        return self.loc + self.scale * delta * math.sqrt(2 / math.pi)

    @property
    def mode(self):
        return self.loc

    @property
    def stddev(self):
        return torch.sqrt(self.variance)
    
    @property
    def variance(self):
        delta = self.alpha / torch.sqrt(1 + self.alpha.pow(2))
        return self.scale.pow(2) * (1 - 2 * delta.pow(2) / math.pi)
    
    @property
    def skewness(self):
        delta = self.alpha / torch.sqrt(1 + self.alpha.pow(2))
        return (4 - math.pi) / 2 * (delta * torch.sqrt(2 / math.pi)).pow(3) / (1 - 2 * delta.pow(2) / math.pi).pow(1.5)

    def __init__(self, loc, scale, alpha, validate_args=None):
        self.loc, self.scale, self.alpha = broadcast_all(loc, scale, alpha)
        if isinstance(loc, Number) and isinstance(scale, Number) and isinstance(alpha, Number):
            batch_shape = torch.Size()
        else:
            batch_shape = self.loc.size()
        super().__init__(batch_shape, validate_args=validate_args)

    def expand(self, batch_shape, _instance=None):
        new = self._get_checked_instance(SkewNormal, _instance)
        batch_shape = torch.Size(batch_shape)
        new.loc = self.loc.expand(batch_shape)
        new.scale = self.scale.expand(batch_shape)
        new.alpha = self.alpha.expand(batch_shape)
        super(SkewNormal, new).__init__(batch_shape, validate_args=False)
        new._validate_args = self._validate_args
        return new

    def sample(self, sample_shape=torch.Size()): 
        # https://stats.stackexchange.com/questions/316314/sampling-from-skew-normal-distribution
        shape = self._extended_shape(sample_shape)
        with torch.no_grad():
            U = torch.randn(shape, dtype=self.loc.dtype, device=self.loc.device)
            V = torch.randn(shape, dtype=self.loc.dtype, device=self.loc.device)
        
            # Adjust for skewness using the alpha parameter
            Z = U + self.alpha * torch.abs(V)

            return self.loc + self.scale * Z / torch.sqrt(1 + self.alpha.pow(2))

    def rsample(self, sample_shape=torch.Size()):
        shape = self._extended_shape(sample_shape)
        U = torch.randn(shape, dtype=self.loc.dtype, device=self.loc.device)
        V = torch.randn(shape, dtype=self.loc.dtype, device=self.loc.device)
    
        # Adjust for skewness using the alpha parameter
        Z = U + self.alpha * torch.abs(V)

        return self.loc + self.scale * Z / torch.sqrt(1 + self.alpha.pow(2))

    def log_prob(self, value):
        if self._validate_args:
            self._validate_sample(value)
        z = (value - self.loc) * self.scale.reciprocal()
        phi = -0.5 * z.pow(2) - math.log(math.sqrt(2 * math.pi))
        Phi = log_norm_cdf(self.alpha*z)
        log_scale = (
            math.log(self.scale) if isinstance(self.scale, Real) else self.scale.log()
        )
        
        return phi + Phi - log_scale + math.log(2)

    def cdf(self, value):
        if self._validate_args:
            self._validate_sample(value)
        raise NotImplementedError("CDF is not implemented due to its complexity.")

    def icdf(self, value):
        raise NotImplementedError("Inverse CDF is not implemented due to its complexity.")

    def entropy(self):
        raise NotImplementedError("Entropy is not implemented due to its complexity.")