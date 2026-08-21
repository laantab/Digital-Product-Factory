import os
os.environ.pop('FACTORY_TEST_MODE', None)
from app import app
print('FACTORY_STARTED', flush=True)
print('TEST_MODE', os.environ.get('FACTORY_TEST_MODE'), flush=True)
app.run(host='127.0.0.1', port=5055, debug=False, use_reloader=False, threaded=True)
