#!/usr/bin/env node
// Read-only companion diagnostic. WARN is advisory and never fails startup.
import {companionStatus,companionLine} from './companion.mjs';
const companion=companionStatus();
const message=companionLine(companion);
console.log(process.argv.includes('--json')?JSON.stringify({status:companion.compatible?'OK':'WARN',companion,message}):message);
