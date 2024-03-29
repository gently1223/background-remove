import errno
import os
import time
import urllib.request
import sys

import numpy as np
import pkg_resources
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from PIL import Image
from skimage import transform
from torchvision import transforms
from tqdm import tqdm

from . import data_loader, u2net


class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


def download_url(url, model_name, output_path):
    if os.path.exists(output_path):
        return

    print(
        f"Downloading model to {output_path}".format(output_path=output_path),
        file=sys.stderr,
    )

    with DownloadProgressBar(
        unit="B", unit_scale=True, miniters=1, desc=url.split("/")[-1]
    ) as t:
        urllib.request.urlretrieve(url, filename=output_path, reporthook=t.update_to)


def load_model(model_name: str = "u2net"):
    if model_name == "u2netp":
        net = u2net.U2NETP(3, 1)
        path = os.path.expanduser("~/.u2net/u2netp.pth")
        download_url(
            "https://www.dropbox.com/s/usb1fyiuh8as5gi/u2netp.pth?dl=1",
            "u2netp.pth",
            path,
        )
    elif model_name == "u2net":
        net = u2net.U2NET(3, 1)
        path = os.path.expanduser("~/.u2net/u2net.pth")
        download_url(
            "https://www.dropbox.com/s/kdu5mhose1clds0/u2net.pth?dl=1",
            "u2net.pth",
            path,
        )
    else:
        print("Choose between u2net or u2netp", file=sys.stderr)

    try:
        if torch.cuda.is_available():
            net.load_state_dict(torch.load(path))
            net.to(torch.device("cuda"))
        else:
            net.load_state_dict(torch.load(path, map_location="cpu",))
    except FileNotFoundError:
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), model_name + ".pth"
        )

    net.eval()

    return net


def norm_pred(d):
    ma = torch.max(d)
    mi = torch.min(d)
    dn = (d - mi) / (ma - mi)

    return dn


def preprocess(image):
    label_3 = np.zeros(image.shape)
    label = np.zeros(label_3.shape[0:2])

    if 3 == len(label_3.shape):
        label = label_3[:, :, 0]
    elif 2 == len(label_3.shape):
        label = label_3

    if 3 == len(image.shape) and 2 == len(label.shape):
        label = label[:, :, np.newaxis]
    elif 2 == len(image.shape) and 2 == len(label.shape):
        image = image[:, :, np.newaxis]
        label = label[:, :, np.newaxis]

    transform = transforms.Compose(
        [data_loader.RescaleT(320), data_loader.ToTensorLab(flag=0)]
    )
    sample = transform({"imidx": np.array([0]), "image": image, "label": label})

    return sample


def predict(net, item):

    sample = preprocess(item)

    with torch.no_grad():

        if torch.cuda.is_available():
            inputs_test = torch.cuda.FloatTensor(sample["image"].unsqueeze(0).float())
        else:
            inputs_test = torch.FloatTensor(sample["image"].unsqueeze(0).float())

        d1, d2, d3, d4, d5, d6, d7 = net(inputs_test)

        pred = d1[:, 0, :, :]
        predict = norm_pred(pred)

        predict = predict.squeeze()
        predict_np = predict.cpu().detach().numpy()
        img = Image.fromarray(predict_np * 255).convert("RGB")

        del d1, d2, d3, d4, d5, d6, d7, pred, predict, predict_np, inputs_test, sample

        return img