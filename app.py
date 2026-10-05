import streamlit as st
from PIL import Image, ImageFile
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import gc

# Allow loading truncated images
ImageFile.LOAD_TRUNCATED_IMAGES = True

# ============================================
# CONFIGURATION: All 5 Wall Art Sizes (300 DPI)
# ============================================

# All 5 standard wall art sizes - used for both 2:3 and 1:1 master types
WALL_ART_SIZES = {
    "2x3": {
        "display_name": "2:3 Ratio (24x36 inches)",
        "file_name": "24x36_2x3ratio",
        "width": 7200,   # 24 * 300 DPI
        "height": 10800, # 36 * 300 DPI
        "covers": "4x6, 6x9, 8x12, 10x15, 12x18, 16x24, 20x30, 24x36"
    },
    "ISO_A1": {
        "display_name": "ISO A1 (23.4x33.1 inches)",
        "file_name": "A1_ISO",
        "width": 7016,   # 23.4 * 300 DPI
        "height": 9933,  # 33.1 * 300 DPI
        "covers": "A5, A4, A3, A2, A1"
    },
    "3x4": {
        "display_name": "3:4 Ratio (18x24 inches)",
        "file_name": "18x24_3x4ratio",
        "width": 5400,   # 18 * 300 DPI
        "height": 7200,  # 24 * 300 DPI
        "covers": "6x8, 9x12, 12x16, 15x20, 18x24"
    },
    "4x5": {
        "display_name": "4:5 Ratio (16x20 inches)",
        "file_name": "16x20_4x5ratio",
        "width": 4800,   # 16 * 300 DPI
        "height": 6000,  # 20 * 300 DPI
        "covers": "4x5, 8x10, 12x15, 16x20"
    },
    "11x14": {
        "display_name": "11x14 inches",
        "file_name": "11x14",
        "width": 3300,   # 11 * 300 DPI
        "height": 4200,  # 14 * 300 DPI
        "covers": "11x14 only"
    }
}

# DPI constant for calculations
DPI = 300


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class ImageStats:
    """Statistics for an uploaded image"""
    width: int
    height: int
    aspect_ratio: float
    megapixels: float
    file_size_mb: float
    format: str
    is_suitable: bool
    quality_warnings: List[str]


@dataclass
class ProcessingResult:
    """Result of processing a single size"""
    size_key: str
    image_bytes: bytes
    file_name: str
    width: int
    height: int
    quality_score: float
    processing_time: float


# ============================================
# VALIDATION & ANALYSIS FUNCTIONS
# ============================================

def analyze_image(image: Image.Image, file_size_bytes: int) -> ImageStats:
    """Analyze an uploaded image and return statistics"""
    width, height = image.size
    aspect_ratio = width / height
    megapixels = (width * height) / 1_000_000
    file_size_mb = file_size_bytes / (1024 * 1024)
    
    warnings = []
    is_suitable = True
    
    # Check minimum resolution
    if width < 3000 or height < 3000:
        warnings.append(f"⚠️ Low resolution ({width}x{height}). Recommended: 7200px minimum")
        is_suitable = False
    elif width < 5000 or height < 5000:
        warnings.append(f"⚡ Medium resolution ({width}x{height}). Some sizes may lose quality")
    
    # Check if image is too small for largest sizes
    if megapixels < 20:
        warnings.append(f"📊 {megapixels:.1f} MP - May not be optimal for largest print sizes")
    
    return ImageStats(
        width=width,
        height=height,
        aspect_ratio=aspect_ratio,
        megapixels=megapixels,
        file_size_mb=file_size_mb,
        format=image.format or "Unknown",
        is_suitable=is_suitable,
        quality_warnings=warnings
    )


def detect_best_master_type(aspect_ratio: float) -> str:
    """Auto-detect the best master type based on image aspect ratio"""
    if 0.9 <= aspect_ratio <= 1.1:
        return "1:1"
    elif aspect_ratio < 0.9:
        return "2:3"  # Portrait
    else:
        return "2:3"  # Default to 2:3 for landscape (will be rotated mentally)


def calculate_quality_score(original_size: Tuple[int, int], target_size: Tuple[int, int]) -> float:
    """Calculate quality score (0-100) based on upscaling/downscaling ratio"""
    orig_pixels = original_size[0] * original_size[1]
    target_pixels = target_size[0] * target_size[1]
    
    if orig_pixels >= target_pixels:
        return 100.0  # Downscaling is always good
    else:
        ratio = orig_pixels / target_pixels
        return min(100, ratio * 100)


# ============================================
# IMAGE PROCESSING FUNCTIONS
# ============================================

def center_crop_and_resize(image: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Center crop image to target aspect ratio then resize"""
    img_width, img_height = image.size
    target_ratio = target_width / target_height
    img_ratio = img_width / img_height
    
    if img_ratio > target_ratio:
        # Image is wider than target - crop sides
        new_width = int(img_height * target_ratio)
        left = (img_width - new_width) // 2
        right = left + new_width
        top = 0
        bottom = img_height
    else:
        # Image is taller than target - crop top/bottom
        new_height = int(img_width / target_ratio)
        top = (img_height - new_height) // 2
        bottom = top + new_height
        left = 0
        right = img_width
    
    # Crop then resize
    cropped = image.crop((left, top, right, bottom))
    resized = cropped.resize((target_width, target_height), Image.LANCZOS)
    
    return resized


def fit_resize_with_background(image: Image.Image, target_width: int, target_height: int, 
                                background_color: Tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """Resize image to fit within target dimensions while maintaining aspect ratio,
    then place on a background of the target size (letterboxing/pillarboxing)"""
    img_width, img_height = image.size
    target_ratio = target_width / target_height
    img_ratio = img_width / img_height
    
    # Convert to RGB if needed
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        # Create background with the same target size
        background = Image.new('RGB', (target_width, target_height), background_color)
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
    else:
        if image.mode != 'RGB':
            image = image.convert('RGB')
        background = Image.new('RGB', (target_width, target_height), background_color)
    
    # Calculate resize dimensions to fit within target
    if img_ratio > target_ratio:
        # Image is wider than target - fit to width
        new_width = target_width
        new_height = int(target_width / img_ratio)
    else:
        # Image is taller than target or same ratio - fit to height
        new_height = target_height
        new_width = int(target_height * img_ratio)
    
    # Resize the image
    resized = image.resize((new_width, new_height), Image.LANCZOS)
    
    # Calculate position to center the resized image
    paste_x = (target_width - new_width) // 2
    paste_y = (target_height - new_height) // 2
    
    # Paste resized image onto background
    if image.mode == 'RGBA':
        # Use alpha channel if present
        background.paste(resized, (paste_x, paste_y), mask=resized.split()[3])
    else:
        background.paste(resized, (paste_x, paste_y))
    
    return background


def get_crop_preview(image: Image.Image, target_width: int, target_height: int, 
                     preview_size: int = 300) -> Tuple[Image.Image, Tuple[int, int, int, int]]:
    """Get a preview of the crop area with bounding box coordinates"""
    img_width, img_height = image.size
    target_ratio = target_width / target_height
    img_ratio = img_width / img_height
    
    if img_ratio > target_ratio:
        new_width = int(img_height * target_ratio)
        left = (img_width - new_width) // 2
        right = left + new_width
        top = 0
        bottom = img_height
    else:
        new_height = int(img_width / target_ratio)
        top = (img_height - new_height) // 2
        bottom = top + new_height
        left = 0
        right = img_width
    
    # Create thumbnail for preview
    preview = image.copy()
    preview.thumbnail((preview_size, preview_size), Image.LANCZOS)
    
    # Scale crop coordinates to preview size
    scale = preview_size / max(img_width, img_height)
    
    return preview, (int(left * scale), int(top * scale), int(right * scale), int(bottom * scale))


def image_to_bytes(image: Image.Image, quality: int = 95, format: str = "JPEG") -> bytes:
    """Convert PIL Image to bytes for download"""
    buffer = io.BytesIO()
    if format.upper() == "JPEG":
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(buffer, format="JPEG", quality=quality, dpi=(300, 300))
    else:
        image.save(buffer, format=format, dpi=(300, 300))
    buffer.seek(0)
    return buffer.getvalue()


def add_white_background(image: Image.Image) -> Image.Image:
    """Add white background to transparent image"""
    if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
        # Create white background
        background = Image.new('RGB', image.size, (255, 255, 255))
        # Convert to RGBA if needed
        if image.mode != 'RGBA':
            image = image.convert('RGBA')
        # Paste image onto white background
        background.paste(image, mask=image.split()[3])  # Use alpha channel as mask
        return background
    elif image.mode != 'RGB':
        return image.convert('RGB')
    return image


def process_single_size(image: Image.Image, size_key: str, size_info: dict, 
                        design_name: str, quality: int, output_format: str,
                        add_white_bg: bool = False, fit_mode: str = "crop") -> ProcessingResult:
    """Process a single size - designed for parallel execution"""
    start_time = time.time()
    
    # Add white background if requested and image has transparency
    if add_white_bg:
        image = add_white_background(image)
    
    # Process based on fit mode
    if fit_mode == "fit":
        # Fit image within target size with background (no cropping)
        processed = fit_resize_with_background(image, size_info["width"], size_info["height"])
    else:
        # Default: crop and resize
        processed = center_crop_and_resize(image, size_info["width"], size_info["height"])
    
    # Calculate quality score
    quality_score = calculate_quality_score(image.size, (size_info["width"], size_info["height"]))
    
    # Convert to bytes
    ext = "jpg" if output_format.upper() == "JPEG" else "png"
    file_name = f"{design_name}_{size_info['file_name']}.{ext}"
    image_bytes = image_to_bytes(processed, quality, output_format)
    
    processing_time = time.time() - start_time
    
    # Clean up
    del processed
    
    return ProcessingResult(
        size_key=size_key,
        image_bytes=image_bytes,
        file_name=file_name,
        width=size_info["width"],
        height=size_info["height"],
        quality_score=quality_score,
        processing_time=processing_time
    )


def process_image_parallel(image: Image.Image, sizes: dict, design_name: str,
                          quality: int, output_format: str, selected_sizes: List[str],
                          max_workers: int = 4, add_white_bg: bool = False, fit_mode: str = "crop") -> List[ProcessingResult]:
    """Process all sizes for an image in parallel"""
    results = []
    
    # Filter to selected sizes only
    sizes_to_process = {k: v for k, v in sizes.items() if k in selected_sizes}
    
    # IMPORTANT: Fully load the image data before parallel processing
    # This prevents "image file is truncated" errors
    image.load()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                process_single_size, image.copy(), size_key, size_info, 
                design_name, quality, output_format, add_white_bg, fit_mode
            ): size_key
            for size_key, size_info in sizes_to_process.items()
        }
        
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                st.error(f"Error processing size {futures[future]}: {str(e)}")
    
    return results


# ============================================
# UTILITY FUNCTIONS
# ============================================

def format_time(seconds: float) -> str:
    """Format seconds into human readable time"""
    if seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"


def estimate_remaining_time(processed: int, total: int, elapsed: float) -> str:
    """Estimate remaining processing time"""
    if processed == 0:
        return "Calculating..."
    
    avg_time = elapsed / processed
    remaining = (total - processed) * avg_time
    return format_time(remaining)


def create_custom_size(width_inches: float, height_inches: float, dpi: int = 300) -> dict:
    """Create a custom size configuration from inches"""
    return {
        "display_name": f"Custom ({width_inches}x{height_inches} inches)",
        "file_name": f"custom_{width_inches}x{height_inches}",
        "width": int(width_inches * dpi),
        "height": int(height_inches * dpi),
        "covers": "Custom size"
    }


# ============================================
# STREAMLIT APP
# ============================================

def main():
    # Page config
    st.set_page_config(
        page_title="WallArt Wizard",
        page_icon="🖼️",
        layout="wide"
    )
    
    # Initialize session state
    if "processed_results" not in st.session_state:
        st.session_state.processed_results = None
    if "processing_stats" not in st.session_state:
        st.session_state.processing_stats = None
    
    # Custom CSS for better styling
    st.markdown("""
    <style>
    .quality-high { color: #28a745; font-weight: bold; }
    .quality-medium { color: #ffc107; font-weight: bold; }
    .quality-low { color: #dc3545; font-weight: bold; }
    .stat-box { 
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem; 
        border-radius: 10px; 
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .warning-box {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Title
    st.title("🖼️ WallArt Wizard")
    st.markdown("**Bulk-resize images to print-ready wall art dimensions at 300 DPI • Parallel Processing • Smart Quality Analysis**")
    
    st.divider()
    
    # ============================================
    # SIDEBAR: Settings
    # ============================================
    
    with st.sidebar:
        st.header("⚙️ Settings")
        
        # Master type selection (for aspect ratio hint only)
        master_type = st.radio(
            "Your Source Image Type:",
            options=["2:3 Ratio (Vertical/Portrait)", "1:1 Square"],
            help="This helps you understand how your image will be processed to fit each size"
        )
        
        st.divider()
        
        # Resize mode selection
        st.subheader("🎯 Resize Mode")
        
        resize_mode = st.radio(
            "How to fit images to target sizes:",
            options=["Crop to fill (may lose edges)", "Fit with background (shows full image)"],
            index=1,  # Default to fit mode
            help="Crop: Crops image to match exact target ratio. Fit: Resizes to fit inside target with white background (no cropping)"
        )
        
        # Convert selection to mode string
        fit_mode = "fit" if "Fit with background" in resize_mode else "crop"
        
        st.divider()
        
        # Size selection - always show all 5 sizes
        st.subheader("📐 Output Sizes (All 5 at 300 DPI)")
        
        # Use unified WALL_ART_SIZES for all master types
        sizes = WALL_ART_SIZES.copy()
        
        # Size checkboxes
        selected_sizes = []
        select_all = st.checkbox("Select All Sizes", value=True)
        
        for key, info in sizes.items():
            if select_all:
                selected_sizes.append(key)
            else:
                if st.checkbox(f"{info['display_name']}", value=True, key=f"size_{key}"):
                    selected_sizes.append(key)
        
        st.divider()
        
        # Custom size option
        st.subheader("📏 Custom Size")
        add_custom = st.checkbox("Add Custom Size", value=False)
        
        if add_custom:
            col1, col2 = st.columns(2)
            with col1:
                custom_width = st.number_input("Width (inches)", min_value=1.0, max_value=60.0, value=16.0, step=0.5)
            with col2:
                custom_height = st.number_input("Height (inches)", min_value=1.0, max_value=60.0, value=20.0, step=0.5)
            
            custom_size = create_custom_size(custom_width, custom_height)
            sizes["custom"] = custom_size
            selected_sizes.append("custom")
            st.success(f"Custom: {custom_size['width']}x{custom_size['height']} px")
        
        st.divider()
        
        # Naming options
        st.subheader("📝 File Naming")
        
        naming_mode = st.radio(
            "Design Name Source:",
            options=["Use original filenames", "Custom name for all designs", "Custom name per design"],
            help="Choose how to name your output files"
        )
        
        custom_prefix = ""
        if naming_mode == "Custom name for all designs":
            custom_prefix = st.text_input(
                "Enter design name:",
                value="MyDesign",
                help="This name will be used for all uploaded images"
            )
        
        st.divider()
        
        # Output options
        st.subheader("🎨 Output Options")
        
        output_format = st.selectbox(
            "Output Format:",
            options=["JPEG", "PNG"],
            help="JPEG for photos, PNG for transparency"
        )
        
        # White background option for transparent images
        add_white_bg = st.checkbox(
            "Add white background to transparent images",
            value=False,
            help="Enable this if your images have transparency and you want a white background instead"
        )
        
        jpg_quality = st.slider(
            "Quality:",
            min_value=80,
            max_value=100,
            value=95,
            help="Higher = better quality but larger file"
        )
        
        st.divider()
        
        # Performance options
        st.subheader("⚡ Performance")
        
        parallel_workers = st.slider(
            "Parallel Workers:",
            min_value=1,
            max_value=8,
            value=4,
            help="More workers = faster but uses more memory"
        )
        
        st.divider()
        
        # Download option
        download_option = st.radio(
            "Download Format:",
            options=["One ZIP per design", "Single master ZIP (all designs)"],
            help="Choose how to organize your downloads"
        )
    
    # ============================================
    # MAIN AREA: Upload and Process
    # ============================================
    
    # Use unified WALL_ART_SIZES for all 5 sizes at 300 DPI
    base_sizes = WALL_ART_SIZES.copy()
    
    if add_custom:
        base_sizes["custom"] = custom_size
    
    # MULTIPLE FILE UPLOAD
    uploaded_files = st.file_uploader(
        "Upload Your Images (Multiple files supported)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        help="Upload multiple upscaled AI images for batch processing"
    )
    
    if uploaded_files:
        st.success(f"✅ {len(uploaded_files)} image(s) uploaded")
        
        # ============================================
        # IMAGE ANALYSIS SECTION
        # ============================================
        
        st.subheader("📊 Image Analysis")
        
        image_stats = {}
        has_warnings = False
        
        analysis_cols = st.columns(min(len(uploaded_files), 4))
        
        for i, uploaded_file in enumerate(uploaded_files):
            col_idx = i % 4
            
            # Get file size
            uploaded_file.seek(0, 2)
            file_size = uploaded_file.tell()
            uploaded_file.seek(0)
            
            # Analyze image
            img = Image.open(uploaded_file)
            stats = analyze_image(img, file_size)
            image_stats[uploaded_file.name] = stats
            
            # Detect best master type
            suggested_type = detect_best_master_type(stats.aspect_ratio)
            
            with analysis_cols[col_idx]:
                st.markdown(f"**{uploaded_file.name[:20]}**")
                st.caption(f"{stats.width}x{stats.height} • {stats.megapixels:.1f}MP • {stats.file_size_mb:.1f}MB")
                
                if stats.quality_warnings:
                    has_warnings = True
                    for warning in stats.quality_warnings:
                        st.warning(warning)
                else:
                    st.success("✅ Excellent quality")
            
            uploaded_file.seek(0)
        
        if has_warnings:
            st.info("💡 **Tip:** For best results, use images at least 7200px on the longest side")
        
        st.divider()
        
        # Custom naming per design option
        design_names = {}
        if naming_mode == "Custom name per design":
            st.subheader("📝 Name Each Design")
            st.info("Enter a custom name for each uploaded image")
            
            cols = st.columns(2)
            for i, uploaded_file in enumerate(uploaded_files):
                col_index = i % 2
                with cols[col_index]:
                    original_name = uploaded_file.name.rsplit('.', 1)[0]
                    custom_name = st.text_input(
                        f"Name for: {uploaded_file.name[:30]}",
                        value=original_name,
                        key=f"name_{i}"
                    )
                    design_names[uploaded_file.name] = custom_name
            
            st.divider()
        
        # Show thumbnails with crop preview
        st.subheader("📤 Uploaded Images with Crop Preview")
        
        show_crop_preview = st.checkbox("Show crop preview for first size", value=True)
        
        cols = st.columns(min(len(uploaded_files), 6))
        for i, uploaded_file in enumerate(uploaded_files):
            col_index = i % 6
            with cols[col_index]:
                img = Image.open(uploaded_file)
                thumb = img.copy()
                thumb.thumbnail((150, 150), Image.LANCZOS)
                st.image(thumb, caption=uploaded_file.name[:15])
            uploaded_file.seek(0)
        
        st.divider()
        
        # ============================================
        # GENERATE BUTTON
        # ============================================
        
        if not selected_sizes:
            st.error("⚠️ Please select at least one size to generate")
        else:
            st.info(f"📐 Will generate **{len(selected_sizes)} sizes** for **{len(uploaded_files)} images** = **{len(selected_sizes) * len(uploaded_files)} total files**")
            
            if st.button("🚀 Generate All Sizes (Parallel Processing)", type="primary"):
                
                # Progress tracking
                progress_bar = st.progress(0)
                status_text = st.empty()
                eta_text = st.empty()
                
                # Store all generated images by design
                all_generated = {}
                processing_times = []
                
                total_files = len(uploaded_files)
                total_operations = total_files * len(selected_sizes)
                current_operation = 0
                start_time = time.time()
                
                # Process each uploaded file
                for file_idx, uploaded_file in enumerate(uploaded_files):
                    # Determine the design name based on naming mode
                    if naming_mode == "Use original filenames":
                        design_name = uploaded_file.name.rsplit('.', 1)[0]
                    elif naming_mode == "Custom name for all designs":
                        design_name = custom_prefix
                        if len(uploaded_files) > 1:
                            design_name = f"{custom_prefix}_{file_idx + 1}"
                    else:  # Custom name per design
                        design_name = design_names.get(uploaded_file.name, uploaded_file.name.rsplit('.', 1)[0])
                    
                    status_text.text(f"⚡ Processing image {file_idx + 1}/{total_files}: {uploaded_file.name}...")
                    
                    # Load image
                    uploaded_file.seek(0)
                    original_image = Image.open(uploaded_file)
                    
                    # Convert to RGB if needed
                    if original_image.mode not in ("RGB", "RGBA"):
                        original_image = original_image.convert("RGB")
                    
                    try:
                        # Process all sizes in parallel
                        results = process_image_parallel(
                            original_image, 
                            base_sizes, 
                            design_name,
                            jpg_quality, 
                            output_format,
                            selected_sizes,
                            max_workers=parallel_workers,
                            add_white_bg=add_white_bg,
                            fit_mode=fit_mode
                        )
                        
                        all_generated[design_name] = results
                        
                        # Update progress
                        current_operation += len(selected_sizes)
                        progress_bar.progress(min(1.0, current_operation / total_operations))
                        
                        # Update ETA
                        elapsed = time.time() - start_time
                        processing_times.extend([r.processing_time for r in results])
                        eta = estimate_remaining_time(current_operation, total_operations, elapsed)
                        eta_text.text(f"⏱️ Estimated time remaining: {eta}")
                        
                    except Exception as e:
                        st.error(f"❌ Error processing {uploaded_file.name}: {str(e)}")
                        continue
                    
                    # Memory cleanup
                    del original_image
                    gc.collect()
                
                total_time = time.time() - start_time
                status_text.text(f"✅ All images processed in {format_time(total_time)}!")
                eta_text.empty()
                
                # Store in session state for caching
                st.session_state.processed_results = all_generated
                st.session_state.processing_stats = {
                    "total_time": total_time,
                    "total_files": sum(len(r) for r in all_generated.values()),
                    "avg_time_per_size": sum(processing_times) / len(processing_times) if processing_times else 0
                }
                
                # ============================================
                # DISPLAY RESULTS
                # ============================================
                
                st.divider()
                st.subheader("📥 Generated Files")
                
                # Stats display
                stats = st.session_state.processing_stats
                stat_cols = st.columns(4)
                
                with stat_cols[0]:
                    st.metric("Total Files", stats["total_files"])
                with stat_cols[1]:
                    st.metric("Processing Time", format_time(stats["total_time"]))
                with stat_cols[2]:
                    st.metric("Avg per Size", f"{stats['avg_time_per_size']:.2f}s")
                with stat_cols[3]:
                    files_per_sec = stats["total_files"] / stats["total_time"] if stats["total_time"] > 0 else 0
                    st.metric("Speed", f"{files_per_sec:.1f} files/sec")
                
                # Quality summary table
                st.subheader("📊 Quality Report")
                
                for design_name, results in all_generated.items():
                    with st.expander(f"**{design_name}** ({len(results)} sizes)", expanded=False):
                        quality_data = []
                        for result in results:
                            quality_class = "high" if result.quality_score >= 90 else "medium" if result.quality_score >= 70 else "low"
                            quality_data.append({
                                "Size": result.file_name,
                                "Dimensions": f"{result.width}x{result.height}",
                                "Quality": f"{result.quality_score:.0f}%",
                                "File Size": f"{len(result.image_bytes) / 1024:.0f} KB",
                                "Time": f"{result.processing_time:.2f}s"
                            })
                        st.table(quality_data)
                
                # ============================================
                # DOWNLOAD OPTIONS
                # ============================================
                
                st.divider()
                
                if "One ZIP per design" in download_option:
                    st.subheader("📦 Download Individual Design ZIPs")
                    
                    cols = st.columns(3)
                    for idx, (design_name, results) in enumerate(all_generated.items()):
                        col_index = idx % 3
                        
                        with cols[col_index]:
                            st.markdown(f"**{design_name}**")
                            total_size = sum(len(r.image_bytes) for r in results) / (1024 * 1024)
                            st.caption(f"{len(results)} sizes • ~{total_size:.1f} MB")
                            
                            # Create ZIP for this design
                            zip_buffer = io.BytesIO()
                            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                                for result in results:
                                    zip_file.writestr(result.file_name, result.image_bytes)
                            
                            zip_buffer.seek(0)
                            
                            st.download_button(
                                label=f"📥 Download {design_name}.zip",
                                data=zip_buffer,
                                file_name=f"{design_name}_WallArt.zip",
                                mime="application/zip",
                                key=f"download_design_{idx}"
                            )
                
                else:
                    st.subheader("📦 Download Master ZIP (All Designs)")
                    
                    # Create one master ZIP with all designs
                    master_zip_buffer = io.BytesIO()
                    
                    with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                        for design_name, results in all_generated.items():
                            for result in results:
                                file_path = f"{design_name}/{result.file_name}"
                                zip_file.writestr(file_path, result.image_bytes)
                    
                    master_zip_buffer.seek(0)
                    total_size = sum(sum(len(r.image_bytes) for r in results) for results in all_generated.values()) / (1024 * 1024)
                    
                    st.download_button(
                        label=f"📥 Download Master ZIP (~{total_size:.1f} MB)",
                        data=master_zip_buffer,
                        file_name="AllDesigns_WallArt_MasterZIP.zip",
                        mime="application/zip",
                        type="primary"
                    )
                
                # ============================================
                # PREVIEW SECTION
                # ============================================
                
                st.divider()
                
                with st.expander("👁️ Preview Generated Sizes (Click to expand)"):
                    for design_name, results in all_generated.items():
                        st.markdown(f"### {design_name}")
                        
                        cols = st.columns(5)
                        for i, result in enumerate(results):
                            col_index = i % 5
                            
                            with cols[col_index]:
                                # Create thumbnail from bytes
                                thumb_img = Image.open(io.BytesIO(result.image_bytes))
                                thumb_img.thumbnail((150, 150), Image.LANCZOS)
                                st.image(thumb_img)
                                
                                quality_emoji = "🟢" if result.quality_score >= 90 else "🟡" if result.quality_score >= 70 else "🔴"
                                st.caption(f"{quality_emoji} {result.quality_score:.0f}%")
                        
                        st.divider()
                
                # ============================================
                # START OVER BUTTON
                # ============================================
                
                st.divider()
                
                col1, col2, col3 = st.columns([1, 2, 1])
                with col2:
                    if st.button("🔄 Start Over / Process New Images", type="secondary"):
                        st.session_state.processed_results = None
                        st.session_state.processing_stats = None
                        st.rerun()
    
    else:
        # Show instructions when no image uploaded
        st.info("👆 Upload one or more images to get started")
        
        st.divider()
        
        # Feature highlights
        st.subheader("✨ New Features")
        
        feature_cols = st.columns(4)
        
        with feature_cols[0]:
            st.markdown("""
            **⚡ Parallel Processing**
            - Process multiple sizes simultaneously
            - 2-4x faster than before
            - Configurable worker count
            """)
        
        with feature_cols[1]:
            st.markdown("""
            **📊 Smart Analysis**
            - Resolution quality warnings
            - Auto aspect ratio detection
            - Quality score per size
            """)
        
        with feature_cols[2]:
            st.markdown("""
            **📏 Custom Sizes**
            - Add any custom dimensions
            - Specify in inches
            - Auto-converts to 300 DPI pixels
            """)
        
        with feature_cols[3]:
            st.markdown("""
            **🎯 Selective Output**
            - Choose specific sizes
            - PNG format support
            - Detailed quality reports
            """)
        
        st.divider()
        
        st.subheader("📖 How to Use This Tool")
        
        st.markdown("""
        1. **Choose Master Type** in the sidebar
           - Select 2:3 if your AI images are vertical/portrait
           - Select 1:1 if your AI images are square
        
        2. **Select Sizes to Generate**
           - Choose which sizes you need
           - Add custom sizes if needed
        
        3. **Upload Multiple Images**
           - Select multiple files at once
           - Tool will analyze quality automatically
           - Supports JPG, PNG, WEBP
        
        4. **Click Generate**
           - Parallel processing for speed
           - Progress bar with ETA
           - Quality scores per size
        
        5. **Download Files**
           - Download individual design ZIPs or master ZIP
           - Upload to Google Drive/Dropbox for Etsy delivery
        """)


if __name__ == "__main__":
    main()