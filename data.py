import pandas as pd
import pickle
import glob
import torch
from numpy import random
from utils import *
from config import *

from PIL import Image
from torchvision import transforms

preprocess_vgg_s = transforms.Compose([
    transforms.Resize(101),
    transforms.CenterCrop(101),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


class Vocab(object):
    def __init__(self, source="pheonix"):
        self.idx2gloss = ["-"]
        self.gloss2idx = {"-": 0}
        self.size = 1
        if source == "pheonix":
            self._build_from_pheonix()

    def _build_from_pheonix(self):
        with open(os.sep.join([ANNO_DIR, "automatic", "trainingClasses.txt"]), 'r') as f:
            lines = f.readlines()

        glosses = []
        for line in lines[1:]:
            gloss = line.split()[0]
            if gloss[-1] != '0':
                continue
            glosses.append(gloss[:-1])

        for idx, gloss in enumerate(glosses):
            self.idx2gloss.append(gloss)
            self.gloss2idx[gloss] = idx + 1

        self.size = len(self.idx2gloss)

        print("Vocabulary of length:", len(self.idx2gloss), "(blank included)")

    def encode(self, text):
        if isinstance(text, str):
            glosses = text.strip().split(" ")
        else:
            glosses = text

        return [self.gloss2idx.get(gloss, 0) for gloss in glosses]

    def encode_batch(self, texts):
        return [self.encode(text) for text in texts]

    def decode(self, vectors, tensor=False):
        if tensor:
            vectors = vectors.detach().cpu().numpy()

        return [self.idx2gloss[idx] for idx in vectors]

    def decode_batch(self, vectors_seq):
        return [self.decode(vectors) for vectors in vectors_seq]


def get_tensor_batch_vgg_s(X, preprocess=preprocess_vgg_s):
    batch = []
    for image_files in X:
        images = [Image.open(img_file) for img_file in image_files]

        video_tensor = torch.stack([preprocess(image) for image in images])
        batch.append(video_tensor)

    batch = torch.stack(batch)
    return torch.Tensor(batch)


def get_pheonix_df(split):
    path = os.sep.join([ANNO_DIR, "manual", split + ".corpus.csv"])
    return pd.read_csv(path, sep='|')


def pad_features(feats, VIDEO_SEQ_LEN):
    padded_feats = np.zeros((VIDEO_SEQ_LEN, feats.shape[1]))
    L = feats.shape[0]
    if L > VIDEO_SEQ_LEN:
        step = L // VIDEO_SEQ_LEN
        left_over = L % VIDEO_SEQ_LEN
        start_idx = step // 2
        start_idxs = []

        for i in range(VIDEO_SEQ_LEN):
            start_idxs.append(start_idx)

            padded_feats[i] = feats[start_idx]
            if np.random.rand() < left_over / VIDEO_SEQ_LEN and L - 1 > start_idx + step * (VIDEO_SEQ_LEN - i - 1):
                start_idx += step + 1
            else:
                start_idx += step
    else:
        for i in range(VIDEO_SEQ_LEN):
            if i < L:
                padded_feats[i] = feats[i]
            else:
                padded_feats[i] = feats[L - 1]

    return padded_feats


def get_batches_vgg_s_pheonix(split, vocab, max_batch_size, shuffle, target_format=2):
    X_path = os.sep.join([VARS_DIR, "X_vgg_s_" + split + ".pkl"])

    y_path = os.sep.join([VARS_DIR, "y_vgg_s_" + split + ".pkl"])

    if os.path.exists(X_path) and os.path.exists(y_path):
        with open(X_path, 'rb') as f:
            X = pickle.load(f)

        with open(y_path, 'rb') as f:
            y = pickle.load(f)

        return X, y

    df = get_pheonix_df(split)
    X = []
    y = []
    for idx in range(df.shape[0]):
        row = df.iloc[idx]
        text = row.annotation
        img_dir = os.sep.join([IMAGES_DIR, split, row.folder])

        image_files = list(glob.glob(img_dir))
        image_files.sort()

        vectors = vocab.encode(text)

        X.append(image_files)
        y.append(vectors)

    X_batches, y_batches = split_batches(X, y, max_batch_size, shuffle, target_format=target_format)

    with open(X_path, 'wb') as f:
        pickle.dump(X_batches, f)

    with open(y_path, 'wb') as f:
        pickle.dump(y_batches, f)

    return X_batches, y_batches


def read_pheonix(split, vocab, save=False, fix_shapes=False):
    suffix = "_" + FRAME_FEAT_MODEL + "_" + split
    if fix_shapes:
        suffix += "_" + str(VIDEO_SEQ_LEN)
    suffix += ".pkl"

    X_path = os.sep.join([VARS_DIR, 'X' + suffix])

    y_path = os.sep.join([VARS_DIR, 'y' + suffix])

    if os.path.exists(X_path) and os.path.exists(y_path):
        with open(X_path, 'rb') as f:
            X = pickle.load(f)

        with open(y_path, 'rb') as f:
            y = pickle.load(f)

        return X, y

    df = get_pheonix_df(split)
    X = []
    y = []
    print("Reading", split, "split")
    start_time = time.time()
    for idx in range(df.shape[0]):
        row = df.iloc[idx]
        text = row.annotation
        feat_path = os.sep.join([VIDEO_FEAT_DIR, split, row.folder]).replace("/*.png", ".npy")
        feats = np.load(feat_path)
        if fix_shapes:
            feats = pad_features(feats, VIDEO_SEQ_LEN)

        vectors = vocab.encode(text)
        if fix_shapes:
            vectors = vectors[:MAX_OUT_LEN]
        elif split == "train" and len(vectors) > feats.shape[0] // 4:
            continue

        X.append(feats)
        y.append(vectors)

        if idx % 25:
            print_progress(idx + 1, df.shape[0], start_time)

    print()

    if save:
        with open(X_path, 'wb') as f:
            pickle.dump(X, f)

        with open(y_path, 'wb') as f:
            pickle.dump(y, f)

    return X, y


def split_batches(X, y, max_batch_size, shuffle=True, target_format=0):
    # target format =>
    # 0 - concatenate targets and return targets(list), target_lengths(list)
    # 1 - pad targets and return targets (numpy matrix), target_lengths
    # anything but 0 and 1 - return just targets

    len_table = dict()

    for idx, feats in enumerate(X):
        l = len(feats)
        if l in len_table:
            len_table[l].append(idx)
        else:
            len_table[l] = [idx]

    X_batches = []
    y_batches = []

    lenghts = list(len_table)

    if shuffle:
        random.shuffle(lenghts)

    for l in lenghts:
        idxs = len_table[l]

        if shuffle:
            random.shuffle(idxs)

        s = 0
        while (s < len(idxs)):
            e = s + max_batch_size
            if e > len(idxs):
                e = len(idxs)

            X_batches.append([X[i] for i in idxs[s:e]])
            if target_format == 0:
                # concatenated targets and lengths
                y_batch = []
                y_lengths = []
                for idx in idxs[s:e]:
                    y_batch += y[idx]
                    y_lengths.append(len(y[idx]))

                y_batch = (y_batch, y_lengths)
            elif target_format == 1:
                # padded targets and lengths
                max_length = float("-inf")
                y_lengths = []

                for idx in idxs[s:e]:
                    max_length = max(max_length, len(y[idx]))

                y_batch = np.zeros((e - s, max_length))

                for i, idx in enumerate(idxs[s:e]):
                    for j in range(len(y[idx])):
                        y_batch[i][j] = y[idx][j]

                    y_lengths.append(len(y[idx]))

                y_batch = (y_batch, y_lengths)

            else:
                # just targets
                y_batch = [y[i] for i in idxs[s:e]]

            y_batches.append(y_batch)

            s += max_batch_size

    return X_batches, y_batches


if __name__ == "__main__":
    vocab = Vocab()
    X_tr, y_tr = read_pheonix("train", vocab)
    df = get_pheonix_df("train")
    for i in range(len(X_tr)):
        if X_tr[i].shape[0] // 4 < y_tr[i].shape[0]:
            print(df.iloc[i].annotation)
            # print(feat_len)
            print(df.iloc[i].folder)

    print(len(X_tr), len(y_tr))
