const {expo} = require('./app.json');

module.exports = {
  ...expo,
  web: {bundler: 'metro', output: 'single'},
  experiments: {...expo.experiments, baseUrl: '/mobile-app'},
};
