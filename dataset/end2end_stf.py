import torch

from dataset.end2end_base import End2EndDataset, random_skip, down_sample

from config import *
from utils import Vocab


class End2EndSTFDataset(End2EndDataset):
    def __init__(self, vocab, split, max_batch_size, augment_frame=True, augment_temp=True):
        if not STF_MODEL.startswith("resnet{2+1}d") or STF_TYPE != 1 or (not USE_STF_FEAT):
            print("Incorrect feat model:", STF_MODEL, STF_TYPE)
            exit(0)
        super(End2EndSTFDataset, self).__init__(vocab, split, max_batch_size, augment_frame, augment_temp)

    def _get_feat(self, row, glosses=None):
        if SOURCE == "PH":
            rel_feat_path = os.path.join(self.split, row.folder.replace("/1/*.png", ".pt"))
        elif SOURCE == "KRSL":
            rel_feat_path = row.video.replace(".mp4", ".pt")
        else:
            return None, None, None

        feat_path = os.path.join(STF_FEAT_DIR,rel_feat_path)
        if not os.path.exists(feat_path):
            return None, None, None

        feat = torch.load(feat_path)
        feat_len = len(feat)

        if feat_len < len(glosses) or len(feat.shape) < 2:
            return None, None, None

        return rel_feat_path, feat, feat_len

    def get_X_batch(self, batch_idxs):
        X_batch = []
        for i in batch_idxs:

            video = torch.load(os.path.join(STF_FEAT_DIR, self.X[i]))
            if self.augment_temp:
                video = down_sample(video, self.X_aug_lens[i] + len(self.X_skipped_idxs[i]))
                video = random_skip(video, self.X_skipped_idxs[i])
                video = torch.stack(video)

            X_batch.append(video)

        X_batch = torch.stack(X_batch)

        return X_batch

    def _get_aug_diff(self, L, out_seq_len):
        return L - out_seq_len


if __name__ == "__main__":
    vocab = Vocab()
    dataset = End2EndSTFDataset(vocab, "train", 32, True, True)

    dataset.start_epoch()

    X_batch, Y_batch, Y_lens = dataset.get_batch(0)

    print(X_batch.size())
    print(Y_batch.size())
    print(Y_lens.size())