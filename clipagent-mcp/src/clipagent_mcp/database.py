import pixeltable as pxt


def init_database() -> None:
    """Initialize Pixeltable database."""
    pxt.init()


def create_video_tables() -> None:
    """Create tables for video processing pipeline."""
    # Videos table - stores uploaded videos
    pxt.create_table(
        "videos",
        {
            "video_id": pxt.String,
            "video_path": pxt.String,
            "filename": pxt.String,
            "duration": pxt.Float,
            "status": pxt.String,  # pending, processing, completed, error
        },
    )

    # Transcripts table - stores audio transcriptions
    pxt.create_table(
        "transcripts",
        {
            "video_id": pxt.String,
            "text": pxt.String,
            "start_time": pxt.Float,
            "end_time": pxt.Float,
        },
    )

    # Frames table - stores sampled video frames
    pxt.create_table(
        "frames",
        {
            "video_id": pxt.String,
            "frame_number": pxt.Int,
            "timestamp": pxt.Float,
            "frame_path": pxt.String,
        },
    )

    # Captions table - stores frame captions
    pxt.create_table(
        "captions",
        {
            "video_id": pxt.String,
            "frame_number": pxt.Int,
            "caption": pxt.String,
        },
    )

    # Embeddings table - stores CLIP embeddings
    pxt.create_table(
        "embeddings",
        {
            "video_id": pxt.String,
            "frame_number": pxt.Int,
            "embedding": pxt.Array,
        },
    )


if __name__ == "__main__":
    init_database()
    create_video_tables()
    print("Database initialized and tables created!")
