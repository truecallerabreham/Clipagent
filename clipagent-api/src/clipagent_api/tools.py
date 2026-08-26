import cv2


def sample_first_frame(video_path: str) -> str:
    cap = cv2.VideoCapture(video_path)
    success, frame = cap.read()
    cap.release()
    if success:
        img_path = video_path.replace(".mp4", "_first_frame.jpg")
        cv2.imwrite(img_path, frame)
        return img_path
    else:
        raise ValueError("Could not read the first frame.")
