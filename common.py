from config import *
import torch
import numpy as np
import cv2
import glob


def preprocess_img(img, mean, std):
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = img.astype(np.float32) / 255
    return (img - mean) / std


def preprocess_2d(img):
    if img.shape[:2] != (IMG_SIZE_2D, IMG_SIZE_2D):
        img = cv2.resize(img, (IMG_SIZE_2D, IMG_SIZE_2D))

    img = preprocess_img(img, np.array([0.485, 0.456, 0.406]), np.array([0.229, 0.224, 0.225]))

    return img


def preprocess_3d(img):
    if img.shape[:2] != (IMG_SIZE_3D, IMG_SIZE_3D):
        img = cv2.resize(img, (IMG_SIZE_3D, IMG_SIZE_3D))

    img = preprocess_img(img, np.array([0.43216, 0.394666, 0.37645]), np.array([0.22803, 0.22145, 0.216989]))

    return img


def get_images(video_dir, size=None):
    images = []
    if SOURCE == "PH":
        image_files = list(glob.glob(video_dir))
        image_files.sort()
        for img_file in image_files:
            img = cv2.imread(img_file)
            if size is not None:
                img = cv2.resize(img, size)
            images.append(img)

    else:
        cap = cv2.VideoCapture(video_dir)
        while True:
            ret, img = cap.read()
            if not ret:
                break

            if size is not None:
                img = cv2.resize(img, size)
            images.append(img)
        cap.release()

    return images


def get_tensor_video(images, preprocess, mode):
    video = []
    for img in images:
        img = preprocess(img)
        video.append(img)

    video_tensor = np.stack(video).astype(np.float32)
    if mode == "2D":
        axes = [0, 3, 1, 2]
    else:
        axes = [3, 0, 1, 2]
    video_tensor = video_tensor.transpose(axes)
    video_tensor = torch.from_numpy(video_tensor)

    return video_tensor


def predict_glosses(preds, decoder):
    out_sentences = []
    if decoder:
        # need to check decoder for permutations of predictions
        beam_result, beam_scores, timesteps, out_seq_len = decoder.decode(preds)
        for i in range(preds.size(0)):
            hypo = list(beam_result[i][0][:out_seq_len[i][0]])
            out_sentences.append(hypo)

    else:
        preds = preds.permute(1, 0, 2).argmax(dim=2).cpu().numpy()
        # glosses_batch = vocab.decode_batch(preds)
        for pred in preds:
            hypo = []
            for i in range(len(pred)):
                if pred[i] == 0 or (i > 0 and pred[i] == pred[i - 1]):
                    continue
                hypo.append(pred[i])

            out_sentences.append(hypo)

    return out_sentences


if __name__ == "__main__":
    np.random.seed(0)

    # print(vocab.idx2gloss)