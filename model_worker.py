"""Run inside each model's existing environment; stdout is a JSON protocol."""
import contextlib
import json
import os
from pathlib import Path
import sys
import time


def run(q):
    from PIL import Image
    if q['method'] == 'trustmark':
        from trustmark import TrustMark
        start = time.perf_counter()
        model = TrustMark(verbose=False, model_type=q.get('model_type', 'Q'))
        image = Image.open(q['image']).convert('RGB')
        if q['action'] == 'watermark':
            model.encode(image, q['message']).save(q['output'])
            return {'image': q['output'], 'seconds': time.perf_counter() - start}
        message, present, schema = model.decode(image)
        return {'detected': bool(present), 'schema': schema,
                'seconds': time.perf_counter() - start}
    import torch
    repo = Path(q['repo']).resolve()
    sys.path.insert(0, str(repo))
    os.chdir(repo)
    device = q.get('device', 'cuda:0')
    if not torch.cuda.is_available():
        raise RuntimeError('This reference adapter requires a CUDA machine.')
    torch.manual_seed(q.get('seed', 42))
    torch.cuda.manual_seed_all(q.get('seed', 42))
    start = time.perf_counter()
    if q['method'] == 'spherical':
        from mapping_method.spherical_watermark import SphericalCodes
        from models.SD_Unet import SD_Unet
        from models.ImagePreprocesser import ImagePreprocesser
        signature = Path(q['key']).resolve()
        codes = SphericalCodes(from_file=signature.stem, keys_path=str(signature.parent),
            N=31, lm=512, lr=512, t=1, K_len=128, batch_size=1,
            latent_shape=(4, 64, 64), device=device)
        model = SD_Unet(q['model'], device, gen_steps=q.get('steps', 50), inv_steps=q.get('steps', 50))
        if q['action'] == 'generate':
            bits = torch.randint(0, 2, (1, codes.lm), device=device)
            model.set_gen_scheduler()
            with torch.no_grad():
                image = model.generate(codes.embed_watermark(bits).float(), q['prompt'])
            image.save(q['output'])
            return {'image': q['output'], 'expected_bits': bits.flatten().int().tolist(),
                    'seconds': time.perf_counter() - start}
        # Resizing is explicit preprocessing, not part of the attack itself.
        image = Image.open(q['image']).convert('RGB')
        original_size = image.size
        image = image.resize((512, 512), Image.Resampling.LANCZOS)
        with torch.no_grad():
            model.set_inv_scheduler()
            recovered = codes.extract_watermark(model.invert(ImagePreprocesser().load_image(image, 512, device)))
        bits = recovered.flatten().int().tolist()
        result = {'recovered_bits': bits, 'seconds': time.perf_counter() - start,
                  'preprocessing': {'input_size': original_size, 'detector_size': [512, 512]}}
        if q.get('expected_bits'):
            expected = q['expected_bits']
            if len(expected) != len(bits):
                raise ValueError('Expected/recovered payload lengths differ.')
            result['bit_accuracy'] = sum(a == b for a, b in zip(expected, bits)) / len(bits)
            result['full_message_match'] = expected == bits
        # No calibrated detector threshold: never invent a binary detection result.
        return result
    if q['method'] == 'prc':
        import pickle
        import numpy as np
        from inversion import stable_diffusion_pipe, generate, exact_inversion
        from src.prc import Encode, Detect, Decode
        from src import pseudogaussians
        # Only trusted local key files: pickle is not a user upload format.
        with open(q['key'], 'rb') as f:
            encoding_key, decoding_key = pickle.load(f)
        pipe = stable_diffusion_pipe(model_id=q['model'], cache_dir=q.get('cache'))
        if q['action'] == 'generate':
            np.random.seed(q.get('seed', 42))
            latents = pseudogaussians.sample(Encode(encoding_key)).reshape(1, 4, 64, 64).to(device)
            image, _, _ = generate(prompt=q['prompt'], pipe=pipe, init_latents=latents,
                num_inference_steps=q.get('steps', 50), gen_seed=q.get('seed', 42))
            image.save(q['output'])
            return {'image': q['output'], 'seconds': time.perf_counter() - start}
        image = Image.open(q['image']).convert('RGB')
        original_size = image.size
        image = image.resize((512, 512), Image.Resampling.LANCZOS)
        z = exact_inversion(image, prompt='', pipe=pipe, inv_order=0,
                            test_num_inference_steps=q.get('steps', 50))
        posterior = pseudogaussians.recover_posteriors(z.double().flatten().cpu(), variances=1.5)
        detection = bool(Detect(decoding_key, posterior))
        decode_success = Decode(decoding_key, posterior) is not None
        return {'detected': detection or decode_success, 'prc_detect': detection,
                'prc_decode_success': decode_success, 'seconds': time.perf_counter() - start,
                'preprocessing': {'input_size': original_size, 'detector_size': [512, 512]}}
    raise ValueError('Unknown method')


if __name__ == '__main__':
    request = json.loads(sys.stdin.read())
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = run(request)
        print(json.dumps(result))
    except Exception as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
