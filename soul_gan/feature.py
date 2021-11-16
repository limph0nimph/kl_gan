from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import torch
import torchvision
from torchvision import transforms
from pytorch_fid.inception import InceptionV3

from soul_gan.utils.metrics import batch_inception

# from functools import wraps
# from main.nnclass import CNN
# from main.util.save_util import save_image_general, save_weight_vgg_feature


class AvgHolder(object):
    cnt: int = 0

    def __init__(self, init_val: Any = 0):
        self.val = init_val

    def upd(self, new_val: Any):
        self.cnt += 1
        alpha = 1.0 / self.cnt
        if isinstance(self.val, list):
            for i in range(len(self.val)):
                self.val[i] = self.val[i] * (1.0 - alpha) + new_val[i]
        else:
            self.val = self.val * (1.0 - alpha) + new_val

    def reset(self):
        if isinstance(self.val, list):
            self.val = [0] * len(self.val)
        else:
            self.val = 0

    @property
    def data(self) -> Any:
        return self.val


class Feature(ABC):
    def __init__(self, n_features=1, callbacks=None):
        self.avg_weight = AvgHolder([0] * n_features)
        self.avg_feature = AvgHolder([0] * n_features)

        self.callbacks = callbacks if callbacks else []

    def log_prob(self, out: List[torch.FloatTensor]) -> torch.FloatTensor:
        lik_f = 0
        # out_lik = out.copy()
        for feature_id in range(len(out)):
            lik_f -= torch.dot(self.weight[feature_id], out[feature_id])

        return lik_f

    def weight_up(self, out: List[torch.FloatTensor], step: float):
        for i in range(len(self.weight)):
            self.weight[i] += step * (out[i] - self.ref_score[i])

    @staticmethod
    def average_feature(feature_method: Callable) -> Callable:
        # @wraps
        def with_avg(self, *args, **kwargs):
            out = feature_method(self, *args, **kwargs)
            self.avg_feature.upd(out)
            return out

        return with_avg

    @staticmethod
    def get_useful_info(feature_out: List[torch.FloatTensor]) -> Dict:
        return {
            f"feature_{i}": val.mean().item()
            for i, val in enumerate(feature_out)
        }

    @staticmethod
    def invoke_callbacks(feature_method: Callable) -> Callable:
        # @wraps
        def with_callbacks(self, *args, **kwargs):
            out = feature_method(self, *args, **kwargs)
            info = self.get_useful_info(out)
            for callback in self.callbacks:
                callback.invoke(info)
            self.avg_feature.upd(out)
            return out

        return with_callbacks

    @abstractmethod
    def __call__(self, x: torch.FloatTensor):
        raise NotImplementedError


class FeatureRegistry:
    registry: Dict = {}

    @classmethod
    def register(cls, name: Optional[str] = None) -> Callable:
        def inner_wrapper(wrapped_class: Feature) -> Callable:
            if name is None:
                name_ = wrapped_class.__name__
            else:
                name_ = name
            cls.registry[name_] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def create_feature(cls, name: str, **kwargs) -> Feature:
        exec_class = cls.registry[name]
        executor = exec_class(**kwargs)
        return executor


@FeatureRegistry.register("inception_score")
class InceptionScoreFeature(Feature):
    def __init__(self, callbacks=None, **kwargs):
        super().__init__(n_features=1, callbacks=callbacks)
        self.device = kwargs.get("device", 0)
        self.model = torchvision.models.inception_v3(
            pretrained=True, transform_input=False
        ).to(self.device)
        self.model.eval()
        self.transform = transforms.Compose(
            [
                transforms.Scale(32),
                transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
            ]
        )

        self.ref_score = kwargs.get("ref_score", [np.log(11.5)])

        self.weight = [0]

    # @staticmethod
    def get_useful_info(self, feature_out: List[torch.FloatTensor]) -> Dict:
        return {
            "inception score": np.exp(
                feature_out[0].mean().item() + self.ref_score[0]
            )
            # for i, val in enumerate(feature_out)
        }

    @Feature.invoke_callbacks
    @Feature.average_feature
    def __call__(self, x) -> List[torch.FloatTensor]:
        pis = batch_inception(self.transform(x), self.model, resize=True)
        score = (
            (pis * (torch.log(pis) - torch.log(pis.mean(0)[None, :])))
            .sum(1)
            .mean(0)
            # torch.kl_div(pis, torch.log(pis.mean(0)[None, :]), reduction=None).sum(1).mean(0)
        )
        score -= self.ref_score[0]
        return [score[None]]


@FeatureRegistry.register()
class InceptionV3MeanFeature(Feature):
    def __init__(self, **kwargs):
        super().__init__()
        self.device = kwargs.get("device", 0)
        self.block_ids = kwargs.get("block_ids", [3])

        self.model = InceptionV3(self.block_ids).to(self.device)

        self.weight = [0] * len(self.block_ids)

    @Feature.invoke_callbacks
    @Feature.average_feature
    def __call__(self, x) -> List[torch.FloatTensor]:
        out = self.model(x)
        for i in range(out):
            out[i] = out[i].mean(1)  # - ref_value

        return out


# class CNNFeature(Feature):
#     """
#     Construct CNN feature methods.

#     Attributes
#     ----------
#     name : str
#         Name of the class, here 'CNNFeature'.
#     layer : tuple
#         A tuple corresponding to the layers to be considered in the log-likelihood.
#     nb_layer : int
#         The number of layers, corresponding to len(self.layer).
#     model_cnn : str
#         Name of the neural network architecture to be used.
#     network : instance of a class
#         The instance of the class is given by CNN, see nnclass.py for more details.
#     beta : float
#         The features are divided by this value.
#         Be careful, the algorithm is sensitive with respect to this value.
#     forward : a function
#         A function taking a tensor as an input and returning the tensor
#           of the output at given layers.
#         See self.forward in nnclass for more details.
#     x0 : torch.tensor
#         4d torch tensor, the examplar image.
#         First dimension is one.
#         Second and third dimension correspond to the width and the height of the image.
#         Fourth dimension is set to 3.
#     feature_init : list
#         A list of length self.nb_layer. Each element of feature_init is a tensor.
#     weight : list
#         Same structure as feature_init and contains weight to compute log-likelihood.
#     regularization : float
#         Inverse of the variance in the a priori white noise (or regularization parameter).

#     Methods
#     -------
#     feature_fun(x)
#         Compute features of x.
#     log_likelihood(out, x)
#         Compute log-likelihood associated with x and features out.
#     weight_up(weight, out, step, weight_old, n_it)
#         Update weight.
#     weight_avg(weight, step, weight_mv_avg, sum_step)
#         Update moving average on weights.
#     save_image(params, x, x_grad, n_it, folder_name, im_number=None)
#         Save images.
#     save_weight(params, feat, w, w_avg, n_it, n_epoch, folder_name)
#         Save weight statistics.
#     """

#     def __init__(self, cnn, params):
#         super().__init__()
#         self.layer = params["layer"]
#         self.nb_layer = len(params["layer"])
#         self.model_cnn = params["model_cnn"]
#         params_CNN = dict()
#         params_CNN["layers"] = params["layer"]
#         params_CNN["model_str"] = params["model_cnn"]
#         self.beta = params["beta"]
#         self.cnn = cnn(params_CNN)
#         self.x0 = params["x0"]
#         self.ref_feature = self(params["x_real"])
#         self.weight = params["weight"]

#     @Feature.average_feature
#     def __call__(self, x):
#         feat = self.cnn(x)
#         x0 = self.x0
#         out = []
#         size_x = x.shape[-2] * x.shape[-1]
#         size_x0 = x0.shape[-2] * x0.shape[-1]
#         ratio_size = size_x0 / size_x
#         for feat_l in feat:
#             ratio_layer = feat_l.shape[-2] * feat_l.shape[-1]
#             ratio_layer = size_x / ratio_layer
#             ratio = ratio_layer * ratio_size / self.beta
#             out.append(feat_l[0].sum((1, 2)) * ratio)
#         return out

# def save_image(self, params, x, x_grad, n_it, folder_name, im_number=None):

#     save_image_general(params, x, x_grad, n_it,
#                        folder_name, im_number)

# def save_weight(self, params, feat, w, w_avg, n_it, n_epoch, fd_name):
#     save_weight_vgg_feature(self, params, feat, w,
#                             w_avg, n_it, n_epoch, fd_name)
