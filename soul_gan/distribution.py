from abc import ABC, abstractmethod
from typing import Any, Callable, Optional, Tuple, Union

import torch
from torch import nn
from torch.distributions import Distribution as torchDist

# from tqdm import tqdm, trange


class Distribution(ABC):
    """Abstract class for distribution"""

    @abstractmethod
    def __call__(self, z: torch.FloatTensor) -> torch.FloatTensor:
        """Computes log probability of input z"""
        raise NotImplementedError


class GANTarget(Distribution):
    def __init__(
        self,
        gen: nn.Module,
        dis: nn.Module,
        proposal: Union[Distribution, torchDist],
    ):
        self.gen = gen
        self.dis = dis
        self.proposal = proposal

    @staticmethod
    def latent_target(
        z: torch.FloatTensor,
        gen: nn.Module,
        dis: nn.Module,
        proposal: Union[Distribution, torchDist],
    ) -> Tuple[torch.FloatTensor, torch.FloatTensor, torch.FloatTensor]:
        dgz = dis(gen(z))
        logp_z = proposal.log_prob(z)
        energy = -(logp_z + dgz)
        return -energy, logp_z, dgz

    def __call__(self, z: torch.FloatTensor) -> torch.FloatTensor:
        logp = self.latent_target(z, self.gen, self.dis, self.proposal)[0]
        return logp


def grad_energy(
    point: torch.FloatTensor,
    log_dens: Union[Distribution, Callable],
    x: Optional[Any] = None,
) -> Tuple[torch.FloatTensor, torch.FloatTensor]:
    point = point.detach().requires_grad_()
    if x is not None:
        energy = -log_dens(z=point, x=x)
    else:
        energy = -log_dens(point)
    grad = torch.autograd.grad(energy.sum(), point)[0]
    return energy, grad
