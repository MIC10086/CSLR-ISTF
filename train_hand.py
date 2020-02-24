import torch
import torch.nn as nn
import numpy as np
from torch.optim import RMSprop, Adam, SGD
from train import predict_glosses
from numpy import random
from models import SLR, weights_init
from torch.utils.data import DataLoader
from dataset import PhoenixHandVideoDataset, hand_video_collate
from utils import Vocab, ProgressPrinter

import Levenshtein as Lev
from config import *

random.seed(0)

torch.backends.cudnn.deterministic = True


# add wer
# may be, investigate LSTM, masking

def train(model, device, vocab, tr_data_loader, val_data_loader, n_epochs):
    optimizer = Adam(model.parameters(), lr=LR)

    data_loaders = {"Train": tr_data_loader, "Val": val_data_loader}
    loss_fn = nn.CTCLoss(zero_infinity=True)

    criterion_phase = CRIT_PHASE_END2END_HAND
    best_wer_path = os.sep.join([VARS_DIR, "best_wer_end2end_hand_" + criterion_phase + ".txt"])
    if os.path.exists(best_wer_path):
        with open(best_wer_path, 'r') as f:
            best_wer = float(f.readline().strip())
    else:
        best_wer = float("inf")

    for epoch in range(1, n_epochs + 1):
        print("Epoch", epoch)
        for phase in ['Train', 'Val']:
            if phase == 'Train':
                model.train()  # Set model to training mode
            else:
                model.eval()

            losses = []
            hypes = []
            gts = []
            with torch.set_grad_enabled(phase == "Train"):
                for idx, (X_batch, x_lens, y_batch, y_lens) in enumerate(data_loaders[phase]):
                    optimizer.zero_grad()

                    X_batch, x_lens = X_batch.to(device), x_lens // 4
                    preds = model(X_batch, x_lens).log_softmax(dim=2)
                    loss = loss_fn(preds, y_batch, x_lens, y_lens)

                    if torch.isnan(loss):
                        print("NAN!!")

                    losses.append(loss.item())

                    if phase == "Train":
                        loss.backward()
                        optimizer.step()

                    out_sentences = predict_glosses(preds, decoder=None)
                    for i in range(len(y_lens)):
                        gts += y_batch[i][:y_lens[i].item()].tolist()

                    hypes += out_sentences

            hypes = "".join([chr(x) for x in hypes])
            gts = "".join([chr(x) for x in gts])
            phase_wer = Lev.distance(hypes, gts) / len(gts) * 100

            phase_loss = np.mean(losses)
            print(phase, "WER:", phase_wer, "Loss:", phase_loss)

            if phase == criterion_phase and phase_wer < best_wer:
                best_wer = phase_wer
                with open(best_wer_path, 'w') as f:
                    f.write(str(best_wer) + "\n")

                torch.save(model.state_dict(), END2END_HAND_MODEL_PATH)
                print("Model Saved")

            # if epoch % 50 == 0:
            #     for param_group in optimizer.param_groups:
            #         param_group['lr'] *= 0.1
            print()
            print()


if __name__ == "__main__":
    vocab = Vocab(source="pheonix")
    tr_dataset = PhoenixHandVideoDataset(vocab, "train", augment=True)
    val_dataset = PhoenixHandVideoDataset(vocab, "dev", augment=False)
    tr_data_loader = DataLoader(tr_dataset, batch_size=END2END_HAND_BATCH_SIZE, shuffle=True,
                                collate_fn=hand_video_collate)
    val_data_loader = DataLoader(val_dataset, batch_size=END2END_HAND_BATCH_SIZE, shuffle=True,
                                 collate_fn=hand_video_collate)

    device = torch.device(DEVICE)
    model = SLR(rnn_hidden=512, vocab_size=vocab.size, temp_fusion_type=2).to(device)
    load = True
    if load and os.path.exists(END2END_HAND_MODEL_PATH):
        model.load_state_dict(torch.load(END2END_HAND_MODEL_PATH))
        print("Model Loaded")
    else:
        model.apply(weights_init)

    train(model, device, vocab, tr_data_loader, val_data_loader, n_epochs=N_EPOCHS_END2END_HAND)