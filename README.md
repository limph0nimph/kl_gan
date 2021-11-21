# Experiments on sampling from GAN with constraints


- [Experiments on sampling from GAN with constraints](#experiments-on-sampling-from-gan-with-constraints)
  - [Getting started](#getting-started)
  - [Usage](#usage)
  - [TODO:](#todo)




## Getting started

```zsh
conda create -n constrained_gan python=3.8
conda activate constrained_gan
```

```zsh
pip install poetry
poetry config virtualenvs.create false --local
```

```zsh
poetry install
```

```zsh
conda activate soul
```

Put CIFAR-10 into directory ```data/cifar10```  using this script

```python
import torchvision.datasets as dset

cifar = dset.CIFAR10(root='data/cifar10', download=True)
```

```zsh
chmod +x run_scripts/*
```

## Usage 

To use wandb:

```
wandb login
```

```zsh
python run.py configs/exp_configs/inception_feature.yml configs/gan_configs/dcgan.yml
```


use pre-commit via 

```zsh
pre-commit run -a
```

## TODO:

* add FID computation
* rewrite loop in run
* write callbacks (IS, saving latents, ...)
* add more features and test
* add reset method to Feature and Callbacks
* add parallelism...


